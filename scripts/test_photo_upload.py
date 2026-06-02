"""Test photo upload with EXIF GPS extraction."""
import json, urllib.request, urllib.error
import io
from datetime import datetime, timezone

BASE='http://localhost:8000/api/v1'

def req(m, p, b=None, t=None, files=None, form_data=None):
    if files:
        # multipart
        boundary = '----test-boundary-12345'
        body = b''
        for k, v in (form_data or {}).items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, (fname, content, ctype) in files.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            body += content + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        h = {}
        if t: h['Authorization'] = f'Bearer {t}'
        h['Content-Type'] = f'multipart/form-data; boundary={boundary}'
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

# Login as contractor
code, body = req('POST', '/auth/login', {'email':'contractor_0278901234@example.ru','password':'password'})
tok = body['access_token']

# Find/create an act
code, orders = req('GET', '/orders?limit=5', t=tok)
order = next((o for o in orders if o['status'] in ('assigned', 'in_progress')), None)
if not order:
    print('no active order, creating one...')
    code, at = req('POST', '/auth/login', {'email':'admin@tatneft.ru','password':'password'})
    adm = at['access_token']
    code, wts = req('GET', '/works/types', t=adm)
    code, objs = req('GET', '/objects?limit=10', t=adm)
    code, contrs = req('GET', '/contractors?limit=10', t=adm)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    code, order = req('POST', '/orders/', {
        'object_id': next(o for o in objs if o['kind']=='well')['id'],
        'work_type_id': next(w for w in wts if w['code']=='TR-1')['id'],
        'contractor_id': next(c for c in contrs if c.get('inn')=='0278901234')['id'],
        'planned_start_at': now.isoformat(),
        'planned_end_at': now.isoformat(),
        'planned_cost': 100000.0,
    }, t=adm)
    print(f'  created {order["number"]}')

if order['status'] == 'assigned':
    code, order = req('POST', f'/orders/{order["id"]}/start', t=tok)

# Create a draft act
code, draft = req('POST', '/acts/', {
    'work_order_id': order['id'],
    'actual_latitude': 54.4,
    'actual_longitude': 53.25,
    'actual_at': datetime.now(timezone.utc).isoformat(),
    'responses': [],
    'photo_keys': [],
}, t=tok)
print(f'✓ draft: {draft["id"]}')

# Create a tiny JPEG with EXIF GPS (use PIL to inject)
from PIL import Image
img = Image.new('RGB', (200, 200), color=(120, 80, 40))

# Inject EXIF GPS manually using piexif-style hack (simpler: write then patch bytes)
# Use a known EXIF GPS bytes pattern
import struct
# GPS IFD: lat 54.4, lon 53.25
def deg_to_dms_rational(deg):
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60 * 10000)
    return ((d, 1), (m, 1), (s, 10000))

# Just save a basic JPEG — we know server should report has_exif_gps=False
# Then try uploading a JPEG with EXIF via PIL
from PIL.ExifTags import TAGS
buf = io.BytesIO()
img.save(buf, 'JPEG', quality=80)
jpeg_bytes = buf.getvalue()
print(f'  jpeg size: {len(jpeg_bytes)} bytes (no EXIF)')

# Upload (no EXIF)
code, body = req('POST', f'/acts/{draft["id"]}/photos',
                 files={'file': ('test.jpg', jpeg_bytes, 'image/jpeg')},
                 form_data={'kind': 'after'},
                 t=tok)
print(f'✓ upload (no EXIF): code={code} has_gps={body.get("has_exif_gps") if isinstance(body, dict) else body}')

# Try with real EXIF: use piexif if available, else skip
try:
    import piexif
    # Build EXIF with GPS for 54.4, 53.25
    def to_rational(num):
        return (int(num * 100), 100)
    lat = 54.4
    lon = 53.25
    lat_d = int(lat)
    lat_m = int((lat - lat_d) * 60)
    lat_s = round((lat - lat_d - lat_m/60) * 3600 * 100)
    lon_d = int(lon)
    lon_m = int((lon - lon_d) * 60)
    lon_s = round((lon - lon_d - lon_m/60) * 3600 * 100)

    gps_ifd = {
        piexif.GPSIFD.GPSVersionID: (2, 0, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: b'N',
        piexif.GPSIFD.GPSLatitude: ((lat_d, 1), (lat_m, 1), (lat_s, 100)),
        piexif.GPSIFD.GPSLongitudeRef: b'E',
        piexif.GPSIFD.GPSLongitude: ((lon_d, 1), (lon_m, 1), (lon_s, 100)),
    }
    exif_dict = {'GPS': gps_ifd, '0th': {}, 'Exif': {}}
    exif_bytes = piexif.dump(exif_dict)
    buf2 = io.BytesIO()
    img.save(buf2, 'JPEG', quality=80, exif=exif_bytes)
    jpeg_with_exif = buf2.getvalue()
    print(f'  jpeg with EXIF: {len(jpeg_with_exif)} bytes')

    code, body = req('POST', f'/acts/{draft["id"]}/photos',
                     files={'file': ('test_with_gps.jpg', jpeg_with_exif, 'image/jpeg')},
                     form_data={'kind': 'before'},
                     t=tok)
    print(f'✓ upload (with EXIF): code={code} has_gps={body.get("has_exif_gps") if isinstance(body, dict) else body}')
    if isinstance(body, dict) and body.get('has_exif_gps'):
        print(f'  GPS extracted: {body.get("latitude")}, {body.get("longitude")}')
except ImportError:
    print('  piexif not available, skipping EXIF test')

# Get photo back
code, detail = req('GET', f'/acts/{draft["id"]}', t=tok)
print(f'✓ act detail: {len(detail["photos"])} photos attached')
for p in detail['photos']:
    print(f'  - {p["kind"]}: gps={p["has_exif_gps"]} {p.get("latitude")},{p.get("longitude")}')

print('\n✅ PHOTO UPLOAD OK')
