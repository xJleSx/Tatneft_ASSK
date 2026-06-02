"""Verify new endpoints work: GET /orders/{id} and POST /acts/{id}/review."""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"

def req(m, p, b=None, t=None):
    d = json.dumps(b).encode() if b else None
    h = {"Content-Type": "application/json"}
    if t:
        h["Authorization"] = f"Bearer {t}"
    r = urllib.request.Request(f"{BASE}{p}", data=d, headers=h, method=m)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]

tok = req("POST", "/auth/login", {"email": "admin@tatneft.ru", "password": "password"})[1]["access_token"]
print("✓ login ok")

# 1) GET /orders/{id}
code, body = req("GET", "/orders/378aca6b-3293-4ca8-b387-cf054e45ff2f", t=tok)
print(f"GET /orders/{{id}} → {code}", "—", body.get("number") if isinstance(body, dict) else body)

# 2) GET /acts?work_order_id=...
code, body = req("GET", "/acts?work_order_id=378aca6b-3293-4ca8-b387-cf054e45ff2f", t=tok)
print(f"GET /acts?work_order_id=... → {code}, count={len(body) if isinstance(body, list) else '?'}")

# 3) Найти pending и отревьюить
acts = req("GET", "/acts?limit=20", t=tok)[1]
pending = [a for a in acts if a["status"] in ("submitted", "delayed_verification")]
print(f"pending acts: {len(pending)}")
if pending:
    a = pending[0]
    code, body = req("POST", f"/acts/{a['id']}/review", {"decision": "confirm", "comment": "test ok"}, t=tok)
    print(f"POST /acts/{{id}}/review → {code}, status={body.get('status') if isinstance(body, dict) else body}")

# 4) 404
code, body = req("GET", "/orders/00000000-0000-0000-0000-000000000000", t=tok)
print(f"GET /orders/000... → {code} (expected 404)")

print("\n✅ all checks done")
