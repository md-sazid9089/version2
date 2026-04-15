#!/usr/bin/env bash
set -o errexit

# GoliTransit Backend Build Script for Render
# ============================================
# This script:
#   1. Verifies we're in the correct backend directory
#   2. Installs Microsoft ODBC Driver 18 for SQL Server (required by pyodbc)
#   3. Checks system dependencies (Python, pip, git)
#   4. Installs Python dependencies from requirements.txt
#   5. Sets up configuration
#   6. Verifies critical imports

echo "=========================================="
echo "GoliTransit Backend Build Script"
echo "=========================================="

# Save and display starting directory
ORIGINAL_DIR=$(pwd)
echo "[INFO] Starting from directory: $ORIGINAL_DIR"

# ─── Verify we're in the backend directory ─────────────────────
if [[ ! -f "requirements.txt" ]]; then
    echo "[ERROR] requirements.txt not found in $(pwd)"
    echo "[ERROR] Please ensure you're running this from the backend directory"
    ls -la
    exit 1
fi

if [[ ! -f "main.py" ]]; then
    echo "[ERROR] main.py not found in $(pwd)"
    echo "[ERROR] This doesn't look like the backend directory"
    exit 1
fi

echo "[✓] Verified backend directory structure"

# ─── Check system dependencies ─────────────────────────────────
echo ""
echo "[INFO] Checking system dependencies..."

# Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "[✓] Found $PYTHON_VERSION"

# pip
if ! command -v pip3 &> /dev/null; then
    echo "[ERROR] pip3 not found"
    exit 1
fi
echo "[✓] Found pip"

# Git (optional but recommended)
if ! command -v git &> /dev/null; then
    echo "[⚠] Git not found (optional)"
else
    echo "[✓] Found git"
fi

# ─── Install Microsoft ODBC Driver 18 for SQL Server ───────────
# Required by pyodbc to connect to Azure SQL (MSSQL).
# Uses the official Microsoft apt repo for Ubuntu 22.04 (Render's OS).
# NOTE: apt-key is deprecated — using gpg --dearmor instead.
echo ""
echo "[INFO] Installing Microsoft ODBC Driver 18 for SQL Server..."

if ! dpkg -l | grep -q msodbcsql18; then
    # Install curl and gpg if not present
    apt-get install -y --no-install-recommends curl gnupg -qq 2>/dev/null || true

    # Add Microsoft GPG key using modern method (no apt-key)
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

    # Add Microsoft Ubuntu 22.04 repo
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \
        > /etc/apt/sources.list.d/mssql-release.list

    apt-get update -qq
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 \
        unixodbc-dev

    rm -rf /var/lib/apt/lists/*
    echo "[✓] ODBC Driver 18 installed successfully"
else
    echo "[✓] ODBC Driver 18 already present — skipping"
fi

echo ""
echo "[INFO] Upgrading pip and setuptools..."
pip3 install --upgrade pip setuptools wheel --quiet

# ─── Install Python dependencies ───────────────────────────────
echo ""
echo "[INFO] Installing Python dependencies from requirements.txt..."
pip3 install -r requirements.txt

if [[ $? -ne 0 ]]; then
    echo "[ERROR] Failed to install Python dependencies"
    exit 1
fi

echo "[✓] Python dependencies installed successfully"

# ─── Verify critical imports ──────────────────────────────────
echo ""
echo "[INFO] Verifying critical Python imports..."

python3 << 'EOF'
import sys

required_modules = [
    'fastapi',
    'uvicorn',
    'pydantic',
    'networkx',
    'osmnx',
    'sqlalchemy',
    'pyodbc',
    'httpx',
]

failed = []
for module in required_modules:
    try:
        __import__(module)
        print(f"  [✓] {module}")
    except ImportError as e:
        print(f"  [✗] {module}: {e}")
        failed.append(module)

if failed:
    print(f"\n[ERROR] Failed to import: {', '.join(failed)}")
    sys.exit(1)

print("\n[✓] All critical imports verified")
EOF

if [[ $? -ne 0 ]]; then
    echo "[ERROR] Import verification failed"
    exit 1
fi

# ─── Verify config.json ──────────────────────────────────────
echo ""
echo "[INFO] Checking configuration..."

if [[ ! -f "config.json" ]]; then
    echo "[ERROR] config.json not found in backend directory"
    echo "[ERROR] Backend requires config.json"
    exit 1
fi

echo "[✓] config.json found in backend directory"

# ─── Summary ───────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "[✓] Build completed successfully!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Python version: $PYTHON_VERSION"
echo "  - Backend directory: $ORIGINAL_DIR"
echo "  - Config file: ../config.json"
echo "  - Ready to start: render-start.sh"
echo ""
echo "Next steps:"
echo "  1. Set required environment variables:"
echo "     - DATABASE_URL (optional, uses config.json by default)"
echo "     - JWT_SECRET_KEY (optional, uses config.json by default)"
echo "     - PORT (default: 8000)"
echo "  2. Run: ./render-start.sh"
echo ""
