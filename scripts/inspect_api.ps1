$token = (Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/api/v1/auth/login' -ContentType 'application/json' -Body '{"email":"admin@tatneft.ru","password":"password"}').access_token
$h = @{Authorization = "Bearer $token"}

Write-Host "=== works/types (1) ==="
(Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/api/v1/works/types' -Headers $h)[0] | ConvertTo-Json -Depth 2

Write-Host "`n=== objects (1) ==="
(Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/api/v1/objects?limit=1' -Headers $h)[0] | ConvertTo-Json -Depth 2

Write-Host "`n=== contractors (1) ==="
(Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/api/v1/contractors?limit=1' -Headers $h)[0] | ConvertTo-Json -Depth 2

Write-Host "`n=== orders (1) ==="
(Invoke-RestMethod -Method Get -Uri 'http://localhost:8000/api/v1/orders?limit=1' -Headers $h)[0] | ConvertTo-Json -Depth 3
