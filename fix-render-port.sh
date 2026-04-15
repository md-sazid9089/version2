#!/usr/bin/env bash

# GoliTransit - Fix Render Port Detection Issues
# =============================================
# This script helps diagnose and fix "No open ports detected" errors on Render
#
# Common Error:
#   ==> No open ports detected, continuing to scan...
#   ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding

set -o errexit

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}==========================================================${NC}"
echo -e "${BLUE}GoliTransit - Render Port Detection Diagnostics${NC}"
echo -e "${BLUE}==========================================================${NC}"
echo ""

# 1. Check render.yaml configuration
echo -e "${BLUE}[1/5] Checking render.yaml configuration...${NC}"
echo ""

if [[ ! -f "render.yaml" ]]; then
    echo -e "${RED}✗ render.yaml not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ render.yaml found${NC}"

# Check for PORT in envVars
if grep -q "key: PORT" render.yaml; then
    echo -e "${GREEN}✓ PORT environment variable is defined${NC}"
    PORT_VALUE=$(grep -A1 "key: PORT" render.yaml | grep "value:" | awk '{print $2}')
    echo "  Default value: $PORT_VALUE"
else
    echo -e "${RED}✗ PORT environment variable not in render.yaml${NC}"
    echo "  Add this to envVars:"
    echo "    - key: PORT"
    echo "      value: 8000"
    exit 1
fi

# Check for healthCheckPath
if grep -q "healthCheckPath:" render.yaml; then
    echo -e "${GREEN}✓ Health check path is defined${NC}"
    HEALTH_PATH=$(grep "healthCheckPath:" render.yaml | awk '{print $2}')
    echo "  Health path: $HEALTH_PATH"
else
    echo -e "${YELLOW}⚠ Health check path not defined${NC}"
    echo "  Add this:"
    echo "    healthCheckPath: /health"
fi

# Check for healthCheckTimeout
if grep -q "healthCheckTimeout:" render.yaml; then
    echo -e "${GREEN}✓ Health check timeout is defined${NC}"
else
    echo -e "${YELLOW}⚠ Health check timeout not defined (should be 30+)${NC}"
fi

echo ""

# 2. Check render-start.sh
echo -e "${BLUE}[2/5] Checking render-start.sh script...${NC}"
echo ""

if [[ ! -f "backend/render-start.sh" ]]; then
    echo -e "${RED}✗ backend/render-start.sh not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ backend/render-start.sh found${NC}"

# Check if using 0.0.0.0
if grep -q "\-\-host 0.0.0.0" backend/render-start.sh; then
    echo -e "${GREEN}✓ Using --host 0.0.0.0 (correct)${NC}"
else
    echo -e "${RED}✗ Not using --host 0.0.0.0${NC}"
    echo "  Change to: --host 0.0.0.0"
fi

# Check if using --workers 1
if grep -q "\-\-workers 1" backend/render-start.sh; then
    echo -e "${GREEN}✓ Using --workers 1 (correct for Render)${NC}"
else
    WORKERS=$(grep "\-\-workers" backend/render-start.sh | grep -o "\-\-workers [0-9]*" | awk '{print $2}')
    if [[ -n "$WORKERS" ]] && [[ "$WORKERS" -gt 1 ]]; then
        echo -e "${RED}✗ Using --workers $WORKERS (should be 1)${NC}"
        echo "  Change to: --workers 1"
    fi
fi

# Check if using exec
if grep -q "^exec uvicorn" backend/render-start.sh; then
    echo -e "${GREEN}✓ Using exec (keeps process in foreground)${NC}"
else
    echo -e "${RED}✗ Not using exec before uvicorn${NC}"
    echo "  Change to: exec uvicorn main:app..."
fi

echo ""

# 3. Check FastAPI health endpoint
echo -e "${BLUE}[3/5] Checking FastAPI health endpoint...${NC}"
echo ""

HEALTH_FOUND=0

# Check in routes
if find backend/routes -name "*.py" -exec grep -l "@app.get.*health\|@router.get.*health" {} \; 2>/dev/null | grep -q .; then
    echo -e "${GREEN}✓ Health endpoint found in routes${NC}"
    HEALTH_FOUND=1
fi

# Check in main.py
if grep -q "@app.get.*health" backend/main.py 2>/dev/null; then
    echo -e "${GREEN}✓ Health endpoint found in main.py${NC}"
    HEALTH_FOUND=1
fi

if [[ $HEALTH_FOUND -eq 0 ]]; then
    echo -e "${RED}✗ Health endpoint not found${NC}"
    echo ""
    echo "  Add this to backend/main.py or routes/health.py:"
    echo ""
    echo "  @app.get('/health')"
    echo "  async def health_check():"
    echo "      return {'status': 'healthy'}"
    echo ""
fi

echo ""

# 4. Test locally
echo -e "${BLUE}[4/5] Testing locally...${NC}"
echo ""

if command -v python3 &>/dev/null; then
    echo -e "${GREEN}✓ Python 3 found${NC}"
    
    # Check if necessary packages are installed
    if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
        echo -e "${GREEN}✓ FastAPI and Uvicorn installed${NC}"
    else
        echo -e "${YELLOW}⚠ FastAPI or Uvicorn not installed${NC}"
        echo "  Run: pip install fastapi uvicorn"
    fi
else
    echo -e "${YELLOW}⚠ Python 3 not found${NC}"
fi

echo ""

# 5. Summary and next steps
echo -e "${BLUE}[5/5] Summary and Recommendations${NC}"
echo ""

echo -e "${GREEN}Port Detection Fix Checklist:${NC}"
echo "  ☐ render.yaml has PORT environment variable = 8000"
echo "  ☐ render.yaml has healthCheckPath: /health"
echo "  ☐ render.yaml has healthCheckTimeout: 30"
echo "  ☐ render-start.sh uses --host 0.0.0.0"
echo "  ☐ render-start.sh uses --workers 1"
echo "  ☐ render-start.sh uses exec uvicorn"
echo "  ☐ FastAPI has @app.get('/health') endpoint"
echo "  ☐ No uvloop (remove --loop uvloop if present)"
echo "  ☐ PYTHONUNBUFFERED=1 in render.yaml"
echo "  ☐ All dependencies in requirements.txt"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Review the checklist above"
echo "  2. Fix any issues in render.yaml and render-start.sh"
echo "  3. Test locally: cd backend && bash render-start.sh"
echo "  4. Verify health: curl http://localhost:8000/health"
echo "  5. Commit changes: git add render.yaml backend/render-start.sh"
echo "  6. Push to GitHub: git push origin main"
echo "  7. Redeploy on Render dashboard"
echo ""

echo -e "${BLUE}Documentation:${NC}"
echo "  - RENDER_PORT_TROUBLESHOOTING.md - Detailed guide"
echo "  - RENDER_QUICK_REFERENCE.md - Quick reference"
echo "  - Render Docs: https://render.com/docs/web-services#port-binding"
echo ""

echo -e "${GREEN}Diagnostic complete!${NC}"
