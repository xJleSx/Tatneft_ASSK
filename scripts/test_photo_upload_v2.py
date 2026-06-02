"""Test EXIF GPS extraction by uploading a JPEG with EXIF generated inside the container."""
import json, urllib.request, urllib.error
import io
from datetime import datetime, timezone

BASE='http://localhost:8000/api/v1'

# Login
def req(m, p, b=None, t=None, files=None, form_data=None):
    if files:
        boundary = '----test-boundary-12345'
        body = b''
        for k, v in (form_data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fname, content, ctype) in files.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            body += content + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        h = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
        if t: h['Authorization'] = f'Bearer {t}'
    else:
        body = json.dumps(b, default=str).encode() if b else None
        h = {'Content-Type':'application/json'}
        if t: h['Authorization'] = f'Bearer {t}'
    r = urllib.request.Request(f'{BASE}{p}', data=body, headers=h, method=m)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]

code, body = req('POST', '/auth/login', {'email':'contractor_0278901234@example.ru','password':'password'})
tok = body['access_token']
print('✓ login')

# Find or create a draft act
code, orders = req('GET', '/orders?limit=5', t=tok)
order = next((o for o in orders if o['status'] == 'in_progress'), None)
if not order:
    code, at = req('POST', '/auth/login', {'email':'admin@tatneft.ru','password':'password'})
    adm = at['access_token']
    code, wts = req('GET', '/works/types', t=adm)
    code, objs = req('GET', '/objects?limit=10', t=adm)
    code, contrs = req('GET', '/contractors?limit=10', t=adm)
    now = datetime.now(timezone.utc)
    code, order = req('POST', '/orders/', {
        'object_id': next(o for o in objs if o['kind']=='well')['id'],
        'work_type_id': next(w for w in wts if w['code']=='TR-1')['id'],
        'contractor_id': next(c for c in contrs if c.get('inn')=='0278901234')['id'],
        'planned_start_at': now.isoformat(),
        'planned_end_at': now.isoformat(),
        'planned_cost': 100000.0,
    }, t=adm)

if order['status'] == 'assigned':
    code, order = req('POST', f'/orders/{order["id"]}/start', t=tok)

code, draft = req('POST', '/acts/', {
    'work_order_id': order['id'],
    'actual_latitude': 54.4,
    'actual_longitude': 53.25,
    'actual_at': datetime.now(timezone.utc).isoformat(),
    'responses': [],
    'photo_keys': [],
}, t=tok)
print(f'✓ draft: {draft["id"]}')

# Generate JPEG with EXIF GPS inside the container
gen_code = '''
import io
from PIL import Image
import piexif

img = Image.new('RGB', (200, 200), color=(80, 120, 60))
lat, lon = 54.4, 53.25
lat_d, lat_m = int(lat), int((lat - int(lat)) * 60)
lat_s = int((lat - int(lat) - lat_m/60) * 3600 * 100)
lon_d, lon_m = int(lon), int((lon - int(lon)) * 60)
lon_s = int((lon - int(lon) - lon_m/60) * 3600 * 100)

gps_ifd = {
    piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
    piexif.GPSIFD.GPSLatitudeRef: b'N',
    piexif.GPSIFD.GPSLatitude: ((lat_d, 1), (lat_m, 1), (lat_s, 100)),
    piexif.GPSIFD.GPSLongitudeRef: b'E',
    piexif.GPSIFD.GPSLongitude: ((lon_d, 1), (lon_m, 1), (lon_s, 100)),
}
exif_dict = {'GPS': gps_ifd, '0th': {}, 'Exif': {}}
exif_bytes = piexif.dump(exif_dict)
buf = io.BytesIO()
img.save(buf, 'JPEG', quality=80, exif=exif_bytes)
with open('/tmp/test_with_gps.jpg', 'wb') as f:
    f.write(buf.getvalue())
print('saved', len(buf.getvalue()), 'bytes')
'''
import subprocess
result = subprocess.run(
    ['docker', 'exec', 'askk-api', 'python', '-c', gen_code],
    capture_output=True, text=True
)
print(f'  generate: {result.stdout.strip() or result.stderr.strip()}')

# Copy file out of container
subprocess.run(['docker', 'cp', 'askk-api:/tmp/test_with_gps.jpg', 'C:\\Users\\JleS\\OpenData\\Local\\Temp\\test_with_gps.jpg'], capture_output=True)
with open(r'C:\Users\JleS\OpenData\Local\Temp\test_with_gps.jpg', 'rb') as f:
    jpeg_bytes = f.read()
print(f'  file: {len(jpeg_bytes)} bytes')

# Upload
code, body = req('POST', f'/acts/{draft["id"]}/photos',
                 files={'file': ('photo.jpg', jpeg_bytes, 'image/jpeg')},
                 form_data={'kind': 'after'},
                 t=tok)
print(f'✓ upload: code={code} has_gps={body.get("has_exif_gps") if isinstance(body, dict) else body}')
if isinstance(body, dict) and body.get('has_exif_gps'):
    print(f'  GPS: {body.get("latitude")}, {body.get("longitude")}')
    print(f'  taken_at: {body.get("taken_at")}')

print('\n✅ EXIF test done')
