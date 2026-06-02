"""
E2E demo-скрипт без UI.

Прогоняет полный цикл:
  1. Admin создаёт наряд-заказ, назначает подрядчика
  2. Подрядчик получает наряд, запрашивает чек-лист
  3. Подрядчик «выехжает на объект» (гео), подписывает акт с заполненным чек-листом
  4. Backend автоматически запускает rule engine → AUTO_CONFIRMED или DELAYED_VERIFICATION
  5. Master подтверждает/отклоняет вручную (для DELAYED_VERIFICATION)
  6. Показываем итоговый state

Требования:
  - Docker-стек запущен (postgres, minio, redis)
  - API на http://localhost:8000
  - БД засеяна (POST /auth/seed)

Запуск:
  pip install requests
  python scripts/demo.py
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

try:
    import requests
except ImportError:
    print("Установи requests: pip install requests", file=sys.stderr)
    sys.exit(1)

BASE = "http://localhost:8000/api/v1"
PASSWORD = "password"

# Учётки из seed (пароль у всех "password")
ADMIN = "admin@tatneft.ru"
CONTRACTOR = "contractor_0278901234@example.ru"  # привязан к ООО «Уралнефтесервис» (inn=0278901234)
MASTER = "master@tatneft.ru"


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n  {title}\n{'=' * 72}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠ {msg}")


class Client:
    def __init__(self, base: str) -> None:
        self.base = base
        self.token: str | None = None

    def login(self, email: str) -> None:
        r = requests.post(
            f"{self.base}/auth/login",
            json={"email": email, "password": PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]

    @property
    def headers(self) -> dict[str, str]:
        assert self.token, "Login first"
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str, **params) -> dict | list:
        r = requests.get(f"{self.base}{path}", headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict | None = None) -> dict:
        r = requests.post(
            f"{self.base}{path}", headers=self.headers, json=body or {}, timeout=15
        )
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, body: dict) -> dict:
        r = requests.patch(f"{self.base}{path}", headers=self.headers, json=body, timeout=15)
        r.raise_for_status()
        return r.json()


def main() -> None:
    section("0. Healthcheck")
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"  API: {r.json()}")

    # --- 1. Admin создаёт наряд-заказ ----------------------------------------
    section("1. Admin: создание наряда-заказа")
    admin = Client(BASE)
    admin.login(ADMIN)
    ok(f"Logged in as {ADMIN}")

    work_types = admin.get("/works/types")
    wt = next(w for w in work_types if w["code"] == "TR-1")
    info(f"Тип работ: {wt['code']} — {wt['name']}")

    objects = admin.get("/objects", kind="well")
    well = objects[0]
    info(f"Объект: {well['name']} ({well['code']}), lat={well['latitude']}, lon={well['longitude']}")

    contractors = admin.get("/contractors")
    contractor = next(c for c in contractors if c["inn"] == "0278901234")
    info(f"Подрядчик: {contractor['name']} (рейтинг {contractor['rating_score']})")

    new_order = admin.post(
        "/orders",
        {
            "object_id": well["id"],
            "work_type_id": wt["id"],
            "contractor_id": contractor["id"],
            "planned_start_at": datetime.now(timezone.utc).isoformat(),
            "planned_end_at": (
                datetime.now(timezone.utc) + timedelta(hours=8)
            ).isoformat(),
            "planned_cost": "120000.00",
            "description": "DEMO: ТР-1 по графику, бригада №3",
        },
    )
    ok(f"Наряд создан: {new_order['number']}, status={new_order['status']}")
    order_id = new_order["id"]

    # --- 2. Подрядчик видит наряд --------------------------------------------
    section("2. Contractor: видит наряд, запрашивает чек-лист")
    cont = Client(BASE)
    cont.login(CONTRACTOR)
    ok(f"Logged in as {CONTRACTOR}")

    my_orders = cont.get("/orders", contractor_id=contractor["id"], status="assigned")
    info(f"Доступно нарядов: {len(my_orders)}")
    this_order = next((o for o in my_orders if o["id"] == order_id), my_orders[0])
    ok(f"Берём в работу: {this_order['number']}")

    template = cont.get(f"/works/types/{wt['id']}/template")
    info(f"Чек-лист: {len(template['steps'])} шагов")
    for s in template["steps"]:
        print(
            f"     {s['order_index']:>2}. {s['title']:<45} "
            f"[{s['data_type']:<8}]"
            f"{'  norm=' + json.dumps(s['norm_json']) if s['norm_json'] else ''}"
        )

    # --- 3. Создание draft-акта ----------------------------------------------
    section("3. Contractor: создание черновика акта")
    now = datetime.now(timezone.utc)
    # Слегка смещаем гео от объекта (имитация реального GPS)
    actual_lat = Decimal(str(well["latitude"])) + Decimal(str(random.uniform(-0.0001, 0.0001)))
    actual_lon = Decimal(str(well["longitude"])) + Decimal(str(random.uniform(-0.0001, 0.0001)))

    # Заполняем чек-лист «хорошими» значениями (в допуске)
    responses = []
    for s in template["steps"]:
        resp: dict = {"step_id": s["id"]}
        if s["data_type"] == "boolean":
            resp["value_bool"] = True
            resp["passed"] = True
        elif s["data_type"] == "numeric" and s["norm_json"]:
            nominal = float(s["norm_json"]["nominal"])
            tol = float(s["norm_json"]["tolerance"])
            value = nominal + random.uniform(-tol * 0.6, tol * 0.6)
            resp["value_numeric"] = str(round(value, 3))
            resp["passed"] = abs(value - nominal) <= tol
        elif s["data_type"] == "text":
            resp["value_text"] = "Замечаний нет"
            resp["passed"] = True
        else:  # photo
            resp["passed"] = True
        responses.append(resp)

    draft = cont.post(
        "/acts",
        {
            "work_order_id": order_id,
            "actual_latitude": str(actual_lat),
            "actual_longitude": str(actual_lon),
            "actual_at": now.isoformat(),
            "responses": responses,
        },
    )
    ok(f"Draft-акт создан: {draft['id']}, status={draft['status']}")

    # --- 4. Submit → auto-check ---------------------------------------------
    section("4. Contractor: подписание акта (submit) → запуск Rule Engine")
    submitted = cont.post(
        f"/acts/{draft['id']}/submit",
        {
            "actual_latitude": str(actual_lat),
            "actual_longitude": str(actual_lon),
            "actual_at": now.isoformat(),
            "responses": responses,
        },
    )
    info(f"Status после submit:       {submitted['status']}")
    info(f"auto_check_passed:         {submitted['auto_check_passed']}")
    info(f"auto_check_score:          {submitted['auto_check_score']}")
    if submitted.get("auto_check_details"):
        details = submitted["auto_check_details"]
        info(f"checklist passed/total:    {details['checklist']['passed']}/{details['checklist']['total']}")
        if "geo" in details:
            info(
                f"geo: distance={details['geo']['distance_m']}m, "
                f"in_radius={details['geo']['in_radius']}"
            )
        if "photos" in details:
            info(f"photos: {details['photos']}")
        if "telemetry" in details:
            changed = details["telemetry"]["params_changed"]
            info(f"telemetry changed params:  {changed}")

    if submitted["status"] == "auto_confirmed":
        ok("АВТО-ПОДТВЕРЖДЁН ✓ — мастеру подтверждать не нужно")
    elif submitted["status"] == "delayed_verification":
        warn("Отправлен на отложенную верификацию — потребуется ручной review")

    # --- 5. Master: ручной review (для delayed_verification) -----------------
    if submitted["status"] == "delayed_verification":
        section("5. Master: ручной review")
        master = Client(BASE)
        master.login(MASTER)
        ok(f"Logged in as {MASTER}")
        reviewed = master.post(
            f"/acts/{submitted['id']}/review",
            {"decision": "confirm", "comment": "Проверено вручную, замечания сняты"},
        )
        ok(f"Решение мастера: {reviewed['status']}, comment={reviewed.get('reviewer_comment')}")
    else:
        section("5. Master: ручной review (пропущен — auto_confirmed)")

    # --- 6. Итоговая сводка --------------------------------------------------
    section("6. Dashboard summary")
    summary = admin.get("/dashboard/summary")
    print(f"     Всего нарядов:        {summary['total_work_orders']}")
    print(f"     Всего актов:          {summary['total_acts']}")
    print(f"     Авто-подтверждено:    {summary['auto_confirmed']}")
    print(f"     На ручной проверке:   {summary['pending_review']}")
    print(f"     Отклонено:            {summary['rejected']}")
    print(f"     Доля авто-подтв.:     {summary['auto_confirmation_rate']:.0%}")
    print(f"     Актов за 30 дней:     {summary['acts_last_30d']}")

    section("Рейтинг подрядчиков")
    rating = admin.get("/dashboard/contractors/ranking")
    for i, c in enumerate(rating, 1):
        print(f"     {i}. {c['name']:<40} score={c['rating_score']:.2f}")

    section("Последние наряды")
    recent = admin.get("/dashboard/orders/recent", limit=5)
    for o in recent:
        print(f"     {o['number']:<24} {o['status']:<22} {o['created_at']}")

    section("✓ DEMO ЗАВЕРШЁН УСПЕШНО")
    print("  Открой http://localhost:8000/docs — там можно посмотреть всё API")
    print("  Открой frontend/index.html — там визуальный дашборд\n")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("API недоступен. Запусти docker compose up -d", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"\nОШИБКА: {e}", file=sys.stderr)
        if hasattr(e, "response") and e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
