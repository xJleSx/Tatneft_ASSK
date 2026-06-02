"""Simulate exactly what the new dashboard modal does."""
import json
import urllib.request

BASE = "http://localhost:8000/api/v1"

def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read()) if resp.status != 204 else None

# 1) Login (как admin, как в дашборде)
token = req("POST", "/auth/login", {"email": "admin@tatneft.ru", "password": "password"})["access_token"]
print("✓ logged in")

# 2) Загрузить dropdowns (как делает loadOrderFormData)
wts = req("GET", "/works/types", token=token)
objs = [o for o in req("GET", "/objects?limit=500", token=token) if o["kind"] == "well"]
contrs = [c for c in req("GET", "/contractors?limit=500", token=token) if c.get("is_active") is not False]
print(f"✓ loaded: {len(wts)} work types, {len(objs)} wells, {len(contrs)} contractors")

# 3) Выбрать: TR-1 (если есть), первую скважину, подрядчика с допуском
tr1 = next((w for w in wts if w["code"] == "TR-1"), wts[0])
print(f"  → work type: {tr1['code']} ({tr1['id'][:8]})")
well = objs[0]
print(f"  → object:    {well['code']} ({well['id'][:8]})")
eligible = [c for c in contrs if tr1["code"] in (c.get("specializations") or "").split(",")]
contractor = eligible[0] if eligible else contrs[0]
print(f"  → contractor:{contractor['name']} (★{contractor['rating_score']})")

# 4) Создать наряд (ровно как форма шлёт)
from datetime import datetime, timezone, timedelta
now = datetime.now(timezone.utc)
body = {
    "object_id": well["id"],
    "work_type_id": tr1["id"],
    "contractor_id": contractor["id"],
    "planned_start_at": now.isoformat(),
    "planned_end_at": (now + timedelta(hours=8)).isoformat(),
    "planned_cost": 120000.0,
    "description": "WEB FORM TEST: ТР-1 по графику",
}
created = req("POST", "/orders/", body, token=token)
print(f"✓ created: {created['number']} (status={created['status']})")

# 5) Проверить что появился в дашборде
recent = req("GET", "/dashboard/orders/recent?limit=5", token=token)
numbers = [o["number"] for o in recent]
assert created["number"] in numbers, f"{created['number']} not in {numbers}"
print(f"✓ visible in dashboard (top {len(numbers)}: {numbers[:3]})")

print("\n✅ WEB FORM FLOW OK")
