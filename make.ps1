<#
Thin wrapper around GNU make for Windows PowerShell.
Uses the same Makefile as *nix. Falls back to direct invocations
of pytest / ruff / mypy / alembic if GNU make is not installed.

Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1           # help
    powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 test
    powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1 ci
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Targets
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSCommandPath
Set-Location -LiteralPath $ProjectRoot

function Find-Make {
    $candidates = @("make", "gmake", "mingw32-make")
    foreach ($c in $candidates) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { return $c }
    }
    return $null
}

$make = Find-Make
if ($make) {
    & $make @Targets
    exit $LASTEXITCODE
}

function Show-Help {
    Write-Host "GNU make not found. Available targets (fallback):" -ForegroundColor Cyan
    Write-Host ""
    @(
        "  test        pytest tests/ -v"
        "  test-fast   pytest tests/ -q"
        "  test-cov    pytest tests/ --cov=app --cov-report=term-missing"
        "  lint        ruff check app tests"
        "  lint-fix    ruff check --fix app tests"
        "  fmt         black app tests + ruff --fix"
        "  typecheck   mypy app"
        "  ci          lint + typecheck + test-fast"
        "  migrate     alembic upgrade head"
        "  revision    alembic revision --autogenerate -m <msg>"
        "  seed        python -m app.mocks.generators.seed"
        "  dev         uvicorn app.main:app --reload"
        "  docker-up   docker compose up -d"
        "  docker-down docker compose down"
        "  docker-logs docker compose logs -f api"
        "  cv-dev      uvicorn cv-service/app.main:app --reload (port 8000)"
        "  cv-test     pytest cv-service/tests/ (MockDetector, no torch)"
        "  cv-lint     ruff + mypy for cv-service"
        "  cv-install  create cv-service/.venv + install deps (no torch)"
        "  cv-smoke    smoke-test YOLOv8 on real photo (needs ultralytics+torch)"
        "  synth-demo  generate synthetic + run YOLOv8 (in-process)"
        "  clean       remove __pycache__, build, dist, .egg-info"
    ) | ForEach-Object { Write-Host $_ }
}

if (-not $Targets -or $Targets.Count -eq 0) {
    Show-Help
    return
}

Push-Location backend
try {
    switch ($Targets[0]) {
        "test"        { pytest tests/ -v }
        "test-fast"   { pytest tests/ -q }
        "test-cov"    { pytest tests/ --cov=app --cov-report=term-missing }
        "lint"        { ruff check app tests }
        "lint-fix"    { ruff check --fix app tests }
        "fmt"         { black app tests; ruff check --fix app tests }
        "typecheck"   { mypy app }
        "ci" {
            ruff check app tests
            if ($LASTEXITCODE) { exit $LASTEXITCODE }
            mypy app
            if ($LASTEXITCODE) { exit $LASTEXITCODE }
            pytest tests/ -q
        }
        "migrate"     { alembic upgrade head }
        "revision" {
            $msg = if ($Targets.Count -gt 1) { $Targets[1] } else { "auto" }
            alembic revision --autogenerate -m $msg
        }
        "seed"        { python -m app.mocks.generators.seed }
        "dev"         { uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 }
        "docker-up"   { Pop-Location; docker compose up -d; return }
        "docker-down" { Pop-Location; docker compose down; return }
        "docker-logs" { Pop-Location; docker compose logs -f api; return }
        "docker-logs-cv" { Pop-Location; docker compose logs -f cv; return }
        "cv-dev"      { Push-Location cv-service; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000; Pop-Location; return }
        "cv-test"     { Pop-Location; python -m pytest cv-service/tests/ -v; return }
        "cv-test-fast"{ Pop-Location; python -m pytest cv-service/tests/ -q; return }
        "cv-lint"     { Pop-Location; ruff check cv-service/app cv-service/tests; python -m mypy cv-service/app; return }
        "cv-install"  {
            Pop-Location
            python -m venv cv-service/.venv
            & cv-service/.venv/Scripts/python.exe -m pip install -U pip
            & cv-service/.venv/Scripts/python.exe -m pip install `
                fastapi 'uvicorn[standard]' pydantic pydantic-settings `
                python-multipart Pillow httpx pytest pytest-asyncio ruff black mypy
            return
        }
        "cv-install-full" {
            Pop-Location
            & cv-service/.venv/Scripts/python.exe -m pip install `
                ultralytics torch --index-url https://download.pytorch.org/whl/cpu
            return
        }
        "cv-smoke"    { Pop-Location; python -m pytest cv-service/tests/test_coco_smoke.py -v; return }
        "synth-demo"  { Pop-Location; python -m app.synth_demo; return }
        "clean" {
            Pop-Location
            Get-ChildItem -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
                Remove-Item -Recurse -Force
            Get-ChildItem -Recurse -Filter *.pyc -ErrorAction SilentlyContinue |
                Remove-Item -Force
            $eggs = Get-ChildItem backend/*.egg-info -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
                backend/build, backend/dist, $eggs
            return
        }
        "help"        { Show-Help }
        default {
            Write-Host "Unknown target: $($Targets[0])" -ForegroundColor Red
            Write-Host "Run: powershell -File make.ps1 (no args) for the list"
            exit 2
        }
    }
} finally {
    if ((Get-Location).Path -like "*backend*") { Pop-Location }
}
