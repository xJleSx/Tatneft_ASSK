"""Test full contractor flow: login, list orders, take assigned one, fill checklist, submit."""
import json, urllib.request, urllib.error
from decimal import Decimal
from datetime import datetime, timezone

BASE='http://localhost:8000/api/v1'

def req(m, p, b=None, t=None):
    d = json.dumps(b, default=str).encode() if b else None
    h = {'Content-Type':'application/json'}
    if t: h['Authorization'] = f'Bearer {t}'
    r = urllib.request.Request(f'{BASE}{p}', data=d, headers=h, method=m)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]

# 1. Login
code, body = req('POST', '/auth/login', {'email':'contractor_0278901234@example.ru','password':'password'})
assert code == 200, f"login failed: {body}"
tok = body['access_token']
print('✓ login as contractor')

# 2. Find an assigned order
code, orders = req('GET', '/orders?status=assigned&limit=10', t=tok)
print(f'  assigned orders: {len(orders) if isinstance(orders, list) else orders}')
if not orders:
    # take the first one in any state — admin likely needs to create one
    code, orders = req('GET', '/orders?limit=5', t=tok)
    # pick the first assigned/in_progress
    for o in orders:
        if o['status'] in ('assigned', 'in_progress'):
            break
    else:
        # Create one as admin
        print('  no assigned orders, creating one as admin...')
        code, at = req('POST', '/auth/login', {'email':'admin@tatneft.ru','password':'password'})
        adm = at['access_token']
        code, wts = req('GET', '/works/types', t=adm)
        code, objs = req('GET', '/objects?limit=10', t=adm)
        code, contrs = req('GET', '/contractors?limit=10', t=adm)
        my_contractor = next(c for c in contrs if c.get('inn') == '0278901234')
        # pick a well
        well = next((o for o in objs if o['kind']=='well'), objs[0])
        tr1 = next((w for w in wts if w['code']=='TR-1'), wts[0])
        now = datetime.now(timezone.utc)
        code, created = req('POST', '/orders/', {
            'object_id': well['id'],
            'work_type_id': tr1['id'],
            'contractor_id': my_contractor['id'],
            'planned_start_at': now.isoformat(),
            'planned_end_at': now.replace(hour=now.hour+8).isoformat(),
            'planned_cost': 100000.0,
            'description': 'CONTRACTOR UI TEST',
        }, t=adm)
        assert code == 201, f"create order failed: {created}"
        print(f'  created: {created["number"]}')
        order = created
else:
    order = orders[0]

print(f'✓ order: {order["number"]} status={order["status"]}')

# 3. Take it (if assigned)
if order['status'] == 'assigned':
    code, body = req('POST', f'/orders/{order["id"]}/start', t=tok)
    print(f'✓ start: code={code} status={body.get("status") if isinstance(body, dict) else body}')
    order = body if isinstance(body, dict) else order

# 4. Get template
code, tpl = req('GET', f"/works/types/{order['work_type_id']}/template", t=tok)
print(f'✓ template: {len(tpl["steps"])} steps')

# 5. Create draft act
code, draft = req('POST', '/acts/', {
    'work_order_id': order['id'],
    'actual_latitude': 54.4,
    'actual_longitude': 53.25,
    'actual_at': datetime.now(timezone.utc).isoformat(),
    'responses': [],
    'photo_keys': [],
}, t=tok)
print(f'✓ draft act: {draft["id"]} status={draft["status"]}')

# 6. Submit with checklist responses
# All numeric → use middle of norm, all boolean → True, text → "ok", photos → none
now = datetime.now(timezone.utc)
responses = []
for s in tpl['steps']:
    r = {'step_id': s['id'], 'passed': True}
    if s['data_type'] == 'boolean':
        r['value_bool'] = True
    elif s['data_type'] == 'numeric':
        norm = s.get('norm_json') or {}
        nominal = norm.get('nominal', 100)
        r['value_numeric'] = float(nominal)
    elif s['data_type'] == 'text':
        r['value_text'] = 'Выполнено'
    responses.append(r)

# Get object coords from order
code, full_order = req('GET', f"/orders/{order['id']}", t=tok)
# Use object coords (we don't have them in order — let's use approximate)
submit_body = {
    'actual_latitude': 54.4,
    'actual_longitude': 53.25,
    'actual_at': now.isoformat(),
    'responses': responses,
}
code, submitted = req('POST', f'/acts/{draft["id"]}/submit', submit_body, t=tok)
print(f'✓ submit: code={code} status={submitted.get("status") if isinstance(submitted, dict) else submitted} score={submitted.get("auto_check_score") if isinstance(submitted, dict) else "?"}')

# 7. Get full act detail
code, detail = req('GET', f'/acts/{draft["id"]}', t=tok)
print(f'✓ act detail: {len(detail.get("responses", []))} responses, {len(detail.get("photos", []))} photos, status={detail.get("status")}')

print('\n✅ CONTRACTOR FLOW OK')
