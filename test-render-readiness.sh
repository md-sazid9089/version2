#!/usr/bin/env bash

# GoliTransit Render Deployment Testing Suite
# ============================================
# This script verifies all components are ready for Render deployment
# Run this before pushing changes to ensure everything works

set -o errexit

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0

print_test() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}TEST: $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ═══════════════════════════════════════════════════════════════
print_test "Project Structure"
# ═══════════════════════════════════════════════════════════════

[[ -d "backend" ]] && pass "backend/ exists" || fail "backend/ not found"
[[ -f "config.json" ]] && pass "config.json exists" || fail "config.json not found"
[[ -f "README.md" ]] && pass "README.md exists" || fail "README.md not found"
[[ -f "requirements.txt" ]] && pass "requirements.txt exists" || fail "requirements.txt not found"

# ═══════════════════════════════════════════════════════════════
print_test "Backend Structure"
# ═══════════════════════════════════════════════════════════════

[[ -f "backend/main.py" ]] && pass "backend/main.py exists" || fail "backend/main.py not found"
[[ -f "backend/requirements.txt" ]] && pass "backend/requirements.txt exists" || fail "backend/requirements.txt not found"
[[ -f "backend/config.py" ]] && pass "backend/config.py exists" || fail "backend/config.py not found"
[[ -d "backend/routes" ]] && pass "backend/routes/ exists" || fail "backend/routes/ not found"
[[ -d "backend/services" ]] && pass "backend/services/ exists" || fail "backend/services/ not found"

# ═══════════════════════════════════════════════════════════════
print_test "Render Configuration Files"
# ═══════════════════════════════════════════════════════════════

[[ -f "render.yaml" ]] && pass "render.yaml exists" || fail "render.yaml not found"
[[ -f "backend/render-build.sh" ]] && pass "backend/render-build.sh exists" || fail "backend/render-build.sh not found"
[[ -f "backend/render-start.sh" ]] && pass "backend/render-start.sh exists" || fail "backend/render-start.sh not found"
[[ -f "RENDER_DEPLOYMENT_GUIDE.md" ]] && pass "RENDER_DEPLOYMENT_GUIDE.md exists" || fail "RENDER_DEPLOYMENT_GUIDE.md not found"

# ═══════════════════════════════════════════════════════════════
print_test "Script Executability"
# ═══════════════════════════════════════════════════════════════

if [[ -x "backend/render-build.sh" ]]; then
    pass "backend/render-build.sh is executable"
else
    warn "backend/render-build.sh is not executable (fixing...)"
    chmod +x backend/render-build.sh
    pass "backend/render-build.sh made executable"
fi

if [[ -x "backend/render-start.sh" ]]; then
    pass "backend/render-start.sh is executable"
else
    warn "backend/render-start.sh is not executable (fixing...)"
    chmod +x backend/render-start.sh
    pass "backend/render-start.sh made executable"
fi

# ═══════════════════════════════════════════════════════════════
print_test "YAML Configuration Syntax"
# ═══════════════════════════════════════════════════════════════

if command -v yamllint &> /dev/null; then
    if yamllint render.yaml 2>/dev/null; then
        pass "render.yaml syntax is valid"
    else
        fail "render.yaml syntax errors found"
    fi
else
    # Basic validation without yamllint
    if grep -q "^services:" render.yaml && grep -q "^databases:" render.yaml; then
        pass "render.yaml appears to have required sections (yamllint not installed)"
    else
        fail "render.yaml missing required sections"
    fi
fi

# ═══════════════════════════════════════════════════════════════
print_test "Backend Dependencies"
# ═══════════════════════════════════════════════════════════════

# Check for critical imports
REQUIRED_PACKAGES=(
    "fastapi"
    "uvicorn"
    "pydantic"
    "networkx"
    "sqlalchemy"
    "pyodbc"
)

for package in "${REQUIRED_PACKAGES[@]}"; do
    if grep -q "^$package" backend/requirements.txt || grep -q "$package==" backend/requirements.txt; then
        pass "$package is in requirements.txt"
    else
        fail "$package not found in requirements.txt"
    fi
done

# ═══════════════════════════════════════════════════════════════
print_test "Configuration File Validity"
# ═══════════════════════════════════════════════════════════════

if python3 -c "import json; json.load(open('config.json'))" 2>/dev/null; then
    pass "config.json is valid JSON"
else
    fail "config.json has JSON syntax errors"
fi

# Verify required config sections
if python3 << 'PYTHON_EOF' 2>/dev/null; then
import json
config = json.load(open('config.json'))
required = ['server', 'database', 'graph']
missing = [s for s in required if s not in config]
if not missing:
    exit(0)
else:
    print(f"Missing: {missing}")
    exit(1)
PYTHON_EOF
    pass "config.json has all required sections"
else
    fail "config.json missing required sections"
fi

# ═══════════════════════════════════════════════════════════════
print_test "Environment Variable Documentation"
# ═══════════════════════════════════════════════════════════════

if grep -q "DATABASE_URL" backend/render-start.sh; then
    pass "DATABASE_URL documented in render-start.sh"
else
    warn "DATABASE_URL not documented"
fi

if grep -q "JWT_SECRET_KEY" backend/render-start.sh; then
    pass "JWT_SECRET_KEY documented in render-start.sh"
else
    warn "JWT_SECRET_KEY not documented"
fi

if grep -q "PORT" backend/render-start.sh; then
    pass "PORT environment variable documented"
else
    warn "PORT not documented"
fi

# ═══════════════════════════════════════════════════════════════
print_test "Health Check Endpoint"
# ═══════════════════════════════════════════════════════════════

if grep -q "/health" backend/routes/health.py 2>/dev/null; then
    pass "Health check endpoint found in backend"
else
    if grep -q "/health" backend/main.py 2>/dev/null; then
        pass "Health check endpoint referenced in main.py"
    else
        warn "Health check endpoint not found (may be defined in routes)"
    fi
fi

# ═══════════════════════════════════════════════════════════════
print_test "Git Integration"
# ═══════════════════════════════════════════════════════════════

if [[ -d ".git" ]]; then
    pass ".git directory found"
    
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        pass "Inside a git repository"
    else
        fail "Not inside a valid git repository"
    fi
else
    warn ".git not found (not a git repository)"
fi

# ═══════════════════════════════════════════════════════════════
print_test "Docker Configuration (Optional)"
# ═══════════════════════════════════════════════════════════════

if [[ -f "docker-compose.yml" ]]; then
    pass "docker-compose.yml found"
else
    warn "docker-compose.yml not found (optional for local dev)"
fi

if [[ -f "backend/Dockerfile" ]]; then
    pass "backend/Dockerfile found"
else
    warn "backend/Dockerfile not found (optional)"
fi

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}DEPLOYMENT READINESS REPORT${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All checks passed! Ready for deployment to Render${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review RENDER_DEPLOYMENT_GUIDE.md"
    echo "  2. Set up sensitive environment variables in Render dashboard"
    echo "  3. Connect your GitHub repository to Render"
    echo "  4. Track deployment progress in Render dashboard"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some checks failed. Please fix the issues above.${NC}"
    echo ""
    echo "Common fixes:"
    echo "  - Ensure render-build.sh and render-start.sh are in backend/"
    echo "  - Check config.json has valid JSON syntax"
    echo "  - Verify all required backend packages are in requirements.txt"
    echo ""
    exit 1
fi
