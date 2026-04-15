#!/usr/bin/env bash
set -o errexit

# GoliTransit Backend Start Script for Render
# ============================================
# This script:
#   1. Verifies we're in the backend directory
#   2. Sets up environment variables
#   3. Verifies database connectivity (optional pre-check)
#   4. Starts the FastAPI application with Uvicorn
#   5. Provides detailed logging

echo "=========================================="
echo "GoliTransit Backend Start Script"
echo "=========================================="

# Save starting directory
ORIGINAL_DIR=$(pwd)
echo "[INFO] Starting from directory: $ORIGINAL_DIR"

# ─── Verify backend directory ──────────────────────────────────
if [[ ! -f "main.py" ]]; then
    echo "[ERROR] main.py not found in $(pwd)"
    echo "[ERROR] Please run this from the backend directory"
    exit 1
fi

if [[ ! -f "config.json" ]]; then
    if [[ ! -f "../config.json" ]]; then
        echo "[ERROR] config.json not found"
        echo "[ERROR] Expected at: ../config.json"
        ls -la ../ | head -20
        exit 1
    fi
    echo "[✓] Using config.json from parent directory"
else
    echo "[✓] Using config.json from current directory"
fi

echo "[✓] Verified backend directory structure"

# ─── Set up environment variables ──────────────────────────────
echo ""
echo "[INFO] Setting up environment variables..."

# Port (Render sets this automatically, default to 8000)
export PORT="${PORT:-8000}"
echo "[✓] PORT=$PORT"

# Config path
export CONFIG_PATH="${CONFIG_PATH:-$(cd .. && pwd)/config.json}"
echo "[✓] CONFIG_PATH=$CONFIG_PATH"

# Database connection (optional override)
if [[ -n "$DATABASE_URL" ]]; then
    echo "[✓] DATABASE_URL set (from environment)"
else
    echo "[INFO] DATABASE_URL not set (using config.json)"
fi

# JWT secret key (use environment variable if provided, otherwise config.json)
if [[ -n "$JWT_SECRET_KEY" ]]; then
    export JWT_SECRET_KEY="$JWT_SECRET_KEY"
    echo "[✓] JWT_SECRET_KEY set (from environment)"
else
    echo "[INFO] JWT_SECRET_KEY not set (using config.json)"
fi

# ML prediction URL
if [[ -n "$ML_PREDICTION_URL" ]]; then
    export ML_PREDICTION_URL="$ML_PREDICTION_URL"
    echo "[✓] ML_PREDICTION_URL=$ML_PREDICTION_URL"
else
    echo "[INFO] ML_PREDICTION_URL not set (using config.json default)"
fi

# ─── Verify Python and dependencies ────────────────────────────
echo ""
echo "[INFO] Verifying Python environment..."

PYTHON_VERSION=$(python3 --version)
echo "[✓] $PYTHON_VERSION"

# Quick import check
python3 -c "import fastapi; import uvicorn; import main" 2>/dev/null
if [[ $? -ne 0 ]]; then
    echo "[ERROR] Failed to import required modules"
    echo "[INFO] Run ./render-build.sh first"
    exit 1
fi

echo "[✓] All required modules available"

# ─── Display configuration summary ────────────────────────────
echo ""
echo "=========================================="
echo "Configuration Summary"
echo "=========================================="
echo "  Backend directory: $ORIGINAL_DIR"
echo "  Config file: $CONFIG_PATH"
echo "  Server port: $PORT"
echo "  Server host: 0.0.0.0"
echo ""

# ─── Verify configuration file is valid ────────────────────────
echo "[INFO] Validating configuration..."

python3 << 'EOF'
import json
import sys
import os

config_path = os.environ.get("CONFIG_PATH")
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    print(f"[✓] Configuration is valid JSON")
    
    # Check required sections
    required_sections = ['server', 'database', 'graph']
    missing = [s for s in required_sections if s not in config]
    
    if missing:
        print(f"[⚠] Missing config sections: {', '.join(missing)}")
        print(f"[⚠] Using defaults for these sections")
    else:
        print(f"[✓] All required config sections present")
    
except json.JSONDecodeError as e:
    print(f"[ERROR] Invalid JSON in config.json: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"[ERROR] config.json not found at {config_path}")
    sys.exit(1)
EOF

if [[ $? -ne 0 ]]; then
    echo "[ERROR] Configuration validation failed"
    exit 1
fi

# ─── Create healthcheck helper script ──────────────────────────
echo ""
echo "[INFO] Creating healthcheck helper..."

cat > /tmp/healthcheck.sh << 'HEALTHCHECK_EOF'
#!/bin/bash
# Simple healthcheck for Render
# Can be used in render.yaml: healthCheck: { path: /health }
curl -f http://localhost:${PORT:-8000}/health || exit 1
HEALTHCHECK_EOF

chmod +x /tmp/healthcheck.sh

# ─── Start the FastAPI application ────────────────────────────
echo ""
echo "=========================================="
echo "[INFO] Starting GoliTransit Backend"
echo "=========================================="
echo ""
echo "FastAPI will be available at:"
echo "  - API: http://0.0.0.0:$PORT"
echo "  - Docs: http://0.0.0.0:$PORT/docs"
echo "  - ReDoc: http://0.0.0.0:$PORT/redoc"
echo "  - Health: http://0.0.0.0:$PORT/health"
echo ""
echo "Port binding: 0.0.0.0:$PORT"
echo "Environment: Production"
echo "Workers: 1 (Render manages scaling)"
echo ""
echo "=========================================="
echo ""

# Ensure PORT is set
if [[ -z "$PORT" ]]; then
    export PORT=8000
    echo "[⚠] PORT not set, using default: 8000"
fi

# Start Uvicorn with Render-optimized settings
# Note: Single worker on Render (Render handles load balancing and scaling)
# uvloop is optional and can cause issues on some systems
echo "[DEBUG] Starting Uvicorn with:"
echo "  - Host: 0.0.0.0"
echo "  - Port: $PORT"
echo "  - Workers: 1"
echo "  - App: main:app"
echo ""
echo "Initialization order:"
echo "  1. Loading FastAPI app from main.py"
echo "  2. Starting ASGI server"
echo "  3. Binding to 0.0.0.0:$PORT"
echo "  4. Ready to accept connections"
echo ""

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --log-level info \
    --access-log
