import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000/api/v1"

# Login
req = urllib.request.Request(
    f"{BASE}/auth/login",
    data=json.dumps({"email": "admin@tatneft.ru", "password": "password"}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read())["access_token"]

H = {"Authorization": f"Bearer {token}"}

def get(path, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items()) if params else ""
    url = f"{BASE}{path}{'?' + qs if qs else ''}"
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
            return data
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}

for label, path, params in [
    ("works/types[0]", "/works/types", {"limit": "1"}),
    ("objects[0]", "/objects", {"limit": "1"}),
    ("contractors[0]", "/contractors", {"limit": "1"}),
    ("orders[0]", "/orders", {"limit": "1"}),
]:
    r = get(path, **params)
    if isinstance(r, list) and r:
        print(f"=== {label} ===")
        print(json.dumps(r[0], ensure_ascii=False, indent=2))
    else:
        print(f"=== {label} ===")
        print(json.dumps(r, ensure_ascii=False, indent=2)[:200])
    print()
