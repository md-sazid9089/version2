#!/usr/bin/env bash

# GoliTransit Local Development Setup & Testing
# ==============================================
# This script helps test the build and start scripts locally
# before deploying to Render

set -o errexit

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# ─── Check if we're in the project root ────────────────────────
print_header "Project Structure Verification"

if [[ ! -d "backend" ]]; then
    print_error "backend/ directory not found"
    print_info "Please run this script from the project root"
    exit 1
fi
print_success "Found backend/ directory"

if [[ ! -f "config.json" ]]; then
    print_error "config.json not found in project root"
    exit 1
fi
print_success "Found config.json"

if [[ ! -f "backend/requirements.txt" ]]; then
    print_error "backend/requirements.txt not found"
    exit 1
fi
print_success "Found backend/requirements.txt"

if [[ ! -f "backend/main.py" ]]; then
    print_error "backend/main.py not found"
    exit 1
fi
print_success "Found backend/main.py"

# ─── Check render scripts ──────────────────────────────────────
print_header "Render Scripts Verification"

if [[ ! -f "backend/render-build.sh" ]]; then
    print_error "backend/render-build.sh not found"
    print_info "Creating render scripts..."
    exit 1
fi
print_success "Found backend/render-build.sh"

if [[ ! -f "backend/render-start.sh" ]]; then
    print_error "backend/render-start.sh not found"
    exit 1
fi
print_success "Found backend/render-start.sh"

# ─── Make scripts executable ───────────────────────────────────
print_header "Setting Execution Permissions"

chmod +x backend/render-build.sh
print_success "Made backend/render-build.sh executable"

chmod +x backend/render-start.sh
print_success "Made backend/render-start.sh executable"

# ─── Run build script in test mode ────────────────────────────
print_header "Building Backend (Test Mode)"

cd backend

print_info "Running: bash render-build.sh"
echo ""

if bash render-build.sh; then
    print_success "Build script completed successfully"
else
    print_error "Build script failed"
    exit 1
fi

# ─── Ask if user wants to start the application ────────────────
print_header "Next Steps"

echo -e "${BLUE}The backend has been built successfully!${NC}"
echo ""
echo "You have two options:"
echo ""
echo "1. Start the backend locally:"
echo "   ${GREEN}bash render-start.sh${NC}"
echo ""
echo "2. Prepare for Render deployment:"
echo "   ${GREEN}git add backend/render-*.sh render.yaml${NC}"
echo "   ${GREEN}git commit -m 'Add Render deployment configuration'${NC}"
echo "   ${GREEN}git push origin main${NC}"
echo ""
echo "For more information, see: ${YELLOW}RENDER_DEPLOYMENT_GUIDE.md${NC}"
echo ""

# Optional: Ask to start the service
read -p "Start the backend now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting backend from: $(pwd)"
    bash render-start.sh
else
    print_info "Skipped. You can start it later with: bash render-start.sh"
fi
