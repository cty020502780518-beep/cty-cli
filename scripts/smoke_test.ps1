# CTY-Cli Smoke Test Script (Windows PowerShell)
# Run from project root: .\scripts\smoke_test.ps1
# Or: powershell -ExecutionPolicy Bypass -File scripts\smoke_test.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " CTY-Cli Smoke Test" -ForegroundColor Cyan
Write-Host " Project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Python version check
Write-Host "[1/7] Checking Python version..." -ForegroundColor Yellow
$pyVer = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found" -ForegroundColor Red
    exit 1
}
Write-Host "  $pyVer" -ForegroundColor Green

# 2. py_compile all Python files
Write-Host "[2/7] Compiling all Python files..." -ForegroundColor Yellow
$pyFiles = Get-ChildItem -Recurse -Filter *.py -Exclude __pycache__ | Where-Object { $_.FullName -notmatch "\\__pycache__\\" }
foreach ($f in $pyFiles) {
    python -m py_compile $f.FullName 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: py_compile failed for $($f.Name)" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  All $($pyFiles.Count) .py files compiled OK" -ForegroundColor Green

# 3. Install dependencies
Write-Host "[3/7] Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt -q 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies installed OK" -ForegroundColor Green

# 4. Editable install
Write-Host "[4/7] Installing cty-cli (editable)..." -ForegroundColor Yellow
pip install -e . -q 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install -e . failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Editable install OK" -ForegroundColor Green

# 5. cty-cli --version
Write-Host "[5/7] Running: python main.py --version" -ForegroundColor Yellow
$ver = python main.py --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: version check failed" -ForegroundColor Red
    exit 1
}
Write-Host "  $ver" -ForegroundColor Green

# 6. pytest (if available)
Write-Host "[6/7] Running tests (if pytest is installed)..." -ForegroundColor Yellow
$pytest = Get-Command pytest -ErrorAction SilentlyContinue
if ($pytest) {
    pytest -v --tb=short 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Some tests failed (check output above)" -ForegroundColor Yellow
    } else {
        Write-Host "  All tests passed" -ForegroundColor Green
    }
} else {
    Write-Host "  pytest not installed (pip install pytest), skipping" -ForegroundColor Yellow
}

# 7. Check required files exist
Write-Host "[7/7] Checking required files..." -ForegroundColor Yellow
$required = @("main.py", "agent.py", "tools.py", "config.py", "requirements.txt", "pyproject.toml", "README.md")
$missing = $required | Where-Object { -not (Test-Path (Join-Path $ProjectRoot $_)) }
if ($missing) {
    Write-Host "ERROR: Missing files: $missing" -ForegroundColor Red
    exit 1
}
Write-Host "  All required files present" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Smoke test PASSED" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
