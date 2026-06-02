"""E2E: детектор аномалий → наряд на диагностику → подрядчик подаёт акт.

Шаги:
  1) логин менеджером
  2) GET /anomalies → берём первую аномалию
  3) POST /orders (work_type_id = DIAGNOSTIC, is_diagnostic=True,
                    priority из severity, defect_ref сгенерён)
  4) логин подрядчиком → POST /orders/{id}/start
  5) подрядчик заполняет чек-лист и подаёт акт
  6) выводим summary
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx

API = "http://localhost:8000/api/v1"


def hr(t: str) -> None:
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def login(c: httpx.Client, email: str, password: str) -> str:
    r = c.post(f"{API}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    with httpx.Client(timeout=15.0, follow_redirects=True) as c:
        hr("1) Логин менеджера")
        mgr_tok = login(c, "manager@tatneft.ru", "password")
        h = auth(mgr_tok)
        print(f"   token={mgr_tok[:24]}…")

        hr("2) Аномалии АСУ ТП")
        r = c.get(f"{API}/anomalies/", headers=h)
        r.raise_for_status()
        anom = r.json()
        print(f"   total={anom['total']}, critical={anom['critical']}, warning={anom['warning']}")
        if not anom["items"]:
            print("   ! нет аномалий — выходим")
            return 1
        first = anom["items"][0]
        print(f"   first: {first['code']} · {first['severity']} · {first['equipment_serial']}")
        print(f"          {first['description']}")
        print(f"          suggested: {first['suggested_work_type_code']}")

        hr("3) Поиск DIAGNOSTIC work_type + подрядчик с допуском")
        wts = c.get(f"{API}/works/types", headers=h).json()
        diag = next((w for w in wts if w["code"] == "DIAGNOSTIC"), None)
        if not diag:
            print("   ! тип DIAGNOSTIC не найден в /works/types — нужно пересеять")
            return 1
        print(f"   DIAGNOSTIC id={diag['id']}")

        contrs = c.get(f"{API}/contractors?limit=100", headers=h).json()
        ok_contr = next(
            (c_ for c_ in contrs
             if "DIAGNOSTIC" in (c_.get("specializations") or "").split(",")),
            None,
        )
        if not ok_contr:
            print("   ! нет подрядчика с допуском DIAGNOSTIC")
            return 1
        print(f"   contractor: {ok_contr['name']} (inn {ok_contr['inn']})")

        hr("4) Создаём наряд на диагностику от аномалии")
        now = datetime.now(timezone.utc)
        order_body = {
            "object_id": first["object_id"],
            "work_type_id": diag["id"],
            "contractor_id": ok_contr["id"],
            "priority": first["severity"],   # critical | warning
            "defect_ref": f"DF-ANOM-{first['equipment_serial']}",
            "is_diagnostic": True,
            "planned_start_at": now.isoformat(),
            "planned_end_at": (now + timedelta(hours=8)).isoformat(),
            "planned_cost": 50_000,
            "description": (
                f"Аномалия АСУ ТП: {first['description']}. "
                f"Рекомендация детектора: {first['suggested_work_type_code']}."
            ),
        }
        r = c.post(f"{API}/orders/", headers=h, json=order_body)
        r.raise_for_status()
        order = r.json()
        print(f"   ✓ {order['number']} · status={order['status']} · priority={order['priority']}")
        print(f"     is_diagnostic={order['is_diagnostic']} · defect_ref={order['defect_ref']}")
        print(f"     work_type_id={order['work_type_id']}")

        hr("5) Логин подрядчика и 'Взять в работу'")
        # Ищем пользователя подрядчика по email-паттерну
        contr_user_email = f"contractor_{ok_contr['inn']}@example.ru"
        try:
            contr_tok = login(c, contr_user_email, "password")
        except httpx.HTTPStatusError:
            # fallback на дефолтного
            contr_tok = login(c, "contractor_0278901234@example.ru", "password")
        print(f"   contractor token={contr_tok[:24]}…")

        ch = auth(contr_tok)
        r = c.post(f"{API}/orders/{order['id']}/start", headers=ch)
        r.raise_for_status()
        order = r.json()
        print(f"   ✓ {order['number']} · status={order['status']} · actual_start_at={order['actual_start_at']}")

        hr("6) Берём шаблон чек-листа DIAGNOSTIC")
        # Нам нужен шаблон по work_type. Эндпоинт /works/types/{id}/template
        r = c.get(f"{API}/works/types/{diag['id']}/template", headers=ch)
        r.raise_for_status()
        tpl = r.json()
        steps = tpl.get("steps", [])
        print(f"   template_id={tpl.get('id')} · steps={len(steps)}")

        hr("7) Подрядчик заполняет и подаёт акт")
        # Сначала создаём акт
        r = c.post(f"{API}/acts/", headers=ch, json={"work_order_id": order["id"]})
        r.raise_for_status()
        act = r.json()
        print(f"   draft act {act['id'][:8]}… · status={act['status']}")

        responses = []
        for s in steps:
            dt = s.get("data_type")
            if dt == "boolean":
                responses.append({"step_id": s["id"], "value_bool": True, "passed": True})
            elif dt == "numeric":
                # Для диагностики — что-то разумное
                responses.append({"step_id": s["id"], "value_numeric": 1.0, "passed": True})
            elif dt == "text":
                responses.append({
                    "step_id": s["id"],
                    "value_text": "Обнаружен износ. Рекомендую ТР-1.",
                    "passed": True,
                })
            else:
                responses.append({"step_id": s["id"], "passed": True})

        submit_body = {
            "actual_latitude": 54.85,
            "actual_longitude": 52.40,
            "actual_at": datetime.now(timezone.utc).isoformat(),
            "responses": responses,
        }
        r = c.post(f"{API}/acts/{act['id']}/submit", headers=ch, json=submit_body)
        r.raise_for_status()
        act = r.json()
        print(f"   ✓ act {act['id'][:8]}… · status={act['status']} · score={act.get('auto_check_score')}")
        if act.get("auto_check_details"):
            d = act["auto_check_details"]
            print(f"     details: passed={d.get('passed')}/{d.get('total')}")

        hr("ИТОГО")
        print(json.dumps({
            "anomaly": first["code"],
            "order": order["number"],
            "diagnostic": order["is_diagnostic"],
            "priority": order["priority"],
            "defect_ref": order["defect_ref"],
            "act_status": act["status"],
            "act_score": act.get("auto_check_score"),
        }, indent=2, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
