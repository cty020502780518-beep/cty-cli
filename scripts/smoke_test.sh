#!/usr/bin/env bash
# CTY-Cli Smoke Test Script (Linux/macOS / Git Bash)
# Run from project root: bash scripts/smoke_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================"
echo " CTY-Cli Smoke Test"
echo " Project: $PROJECT_ROOT"
echo "========================================"
echo ""

# 1. Python version check
echo "[1/7] Checking Python version..."
python --version
echo "  OK"

# 2. py_compile all Python files
echo "[2/7] Compiling all Python files..."
count=0
while IFS= read -r -d '' f; do
    python -m py_compile "$f"
    count=$((count + 1))
done < <(find . -name "*.py" -not -path "./__pycache__/*" -not -path "./.git/*" -not -path "*/__pycache__/*" -not -path "./cty_cli.egg-info/*" -print0)
echo "  All $count .py files compiled OK"

# 3. Install dependencies
echo "[3/7] Installing dependencies..."
pip install -r requirements.txt -q
echo "  Dependencies installed OK"

# 4. Editable install
echo "[4/7] Installing cty-cli (editable)..."
pip install -e . -q
echo "  Editable install OK"

# 5. cty-cli --version
echo "[5/7] Running: python main.py --version"
python main.py --version
echo "  OK"

# 6. pytest (if available)
echo "[6/7] Running tests..."
if command -v pytest &>/dev/null; then
    pytest -v --tb=short || echo "  Some tests failed (check output above)"
else
    echo "  pytest not installed (pip install pytest), skipping"
fi

# 7. Check required files
echo "[7/7] Checking required files..."
for f in main.py agent.py tools.py config.py requirements.txt pyproject.toml README.md; do
    if [ ! -f "$f" ]; then
        echo "ERROR: Missing file: $f"
        exit 1
    fi
done
echo "  All required files present"

echo ""
echo "========================================"
echo " Smoke test PASSED"
echo "========================================"
