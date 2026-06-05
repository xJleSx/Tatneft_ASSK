$groups = @{
  "1: scaffold + data layer" = @("1d73aec","ff3d582","ee0d86a","2caae93","bdc2e4b")
  "2: backend core" = @("0bde7ae","e03450d","f551f36")
  "3: full frontend + integration" = @("a16788f","63a3a1a","5265e5c","7aef80a")
}
foreach ($g in $groups.Keys) {
  Write-Host "=== $g ==="
  foreach ($c in $groups[$g]) {
    Write-Host "--- $c ---"
    git show --stat --format="%s" $c 2>&1 | Select-Object -First 25
    Write-Host ""
  }
}
