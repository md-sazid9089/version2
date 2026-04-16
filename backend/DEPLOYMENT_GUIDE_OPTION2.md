# Deployment Guide - Option 2 Graph Caching

## Local Development

### Setup

```bash
# 1. Clone and install
git clone <repo>
cd backend
pip install -r requirements.txt

# 2. Build graph cache (one-time)
python build_graph_cache.py

# 3. Start server with cache
export USE_GRAPH_CACHE=1
export PRELOAD_GRAPH=1
python main.py
```

### Expected Output

```
[startup] Creating database tables...
[startup] Database tables created/verified
[startup] Preloading graph (cache=enabled)...
[startup] Loading graph for: Dhaka, Bangladesh (center=23.7639,90.4066, radius=2000m)
[GraphService] ✓ Loaded from cache in 145.3ms
[startup] ✓ Graph loaded in 0.15s (4,563 nodes, 10,892 edges)
...
Uvicorn running on http://0.0.0.0:8000
```

---

## Docker Deployment (Local)

### Dockerfile

The existing `backend/Dockerfile` should work as-is:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code AND cached graph
COPY . .

# Run
CMD ["python", "main.py"]
```

### Build & Run

```bash
cd backend
docker build -t golitransit-backend:latest .

docker run -e USE_GRAPH_CACHE=1 -e PRELOAD_GRAPH=1 \
  -p 8000:8000 \
  golitransit-backend:latest
```

---

## Production Deployment (Render)

### Prerequisites

- Graph cache already committed to git: `backend/data/osm_cache/dhaka_bangladesh_graph.pkl`
- Render account with connected GitHub repo

### Step 1: Configure Render

In `render.yaml`:

```yaml
services:
  - type: web
    name: golitransit-backend
    env: python
    plan: standard
    buildCommand: "pip install -r backend/requirements.txt"
    startCommand: "python -u backend/main.py"
    healthCheckPath: /health
    
    # Environment variables
    envVars:
      - key: USE_GRAPH_CACHE
        value: "1"
      - key: PRELOAD_GRAPH
        value: "1"
      - key: GRAPH_CACHE_DIR
        value: "./data/osm_cache"
    
    # Ensure graph cache is deployed
    routes:
      - path: /health
        port: 8000
```

### Step 2: Deploy

```bash
# Commit graph cache to git
git add backend/data/osm_cache/dhaka_bangladesh_graph.pkl
git commit -m "feat: add OSM graph cache"
git push origin main

# Render automatically deploys from git
# Check: https://dashboard.render.com
```

### Step 3: Monitor

```bash
# Check startup logs
# Should see: "[startup] ✓ Graph loaded in 0.15s"

# Test API
curl https://your-render-app.onrender.com/health
```

---

## GitHub Actions CI/CD

### Auto-rebuild Graph on Merge (Optional)

If you want the graph cache to auto-update when OSM data changes:

**.github/workflows/update-graph-cache.yml**

```yaml
name: Update Graph Cache

on:
  schedule:
    # Run weekly on Monday at 2 AM UTC
    - cron: '0 2 * * 1'
  workflow_dispatch:  # Allow manual trigger

jobs:
  rebuild-cache:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
      
      - name: Build graph cache
        run: |
          cd backend
          python build_graph_cache.py
      
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          if git diff --quiet backend/data/osm_cache/; then
            echo "No changes to cache"
          else
            git add backend/data/osm_cache/dhaka_bangladesh_graph.pkl
            git add backend/data/osm_cache/dhaka_bangladesh_graph_meta.json
            git commit -m "chore: update graph cache from OSM"
            git push
          fi
```

---

## Environment Checklist

### Development (.env.local)

```env
# Database
DB_USER=root
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=3306
DB_NAME=golitransit

# JWT
JWT_SECRET_KEY=dev-secret-change-in-production

# Graph Caching (Option 2)
USE_GRAPH_CACHE=1
PRELOAD_GRAPH=1
GRAPH_CACHE_DIR=./data/osm_cache

# Server
BACKEND_HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Production (Render Dashboard)

In Render dashboard -> Environment Variables:

```
USE_GRAPH_CACHE = 1
PRELOAD_GRAPH = 1
GRAPH_CACHE_DIR = ./data/osm_cache
DB_USER = <production-db-user>
DB_PASSWORD = <production-db-password>
DB_HOST = <production-db-host>
DB_PORT = 3306
DB_NAME = golitransit_prod
JWT_SECRET_KEY = <production-secret-key>
CORS_ORIGINS = https://your-domain.com,https://www.your-domain.com
```

---

## Verification Checklist

After deployment, verify:

- [ ] API health check responds: `curl /health`
- [ ] Graph loaded in startup logs: `grep "Graph loaded" logs`
- [ ] Response times normal: `curl /route/...` < 100ms
- [ ] Cache hit rate monitoring: Logs show cache loads instead of OSM

### Quick Health Check

```bash
# SSH into Render instance
render exec -i backend /bin/bash

# Check graph status
ps aux | grep main  # Verify running
curl localhost:8000/graph/snapshot | jq '.stats'
```

---

## Rollback

If cache is corrupted:

```bash
# Option 1: Disabled cache, force fresh download
export USE_GRAPH_CACHE=0
export PRELOAD_GRAPH=1
# Restart - will download from OSM (~30s slower)

# Option 2: Rebuild cache locally and redeploy
cd backend
python build_graph_cache.py --force-download
git add -A
git commit -m "chore: rebuild corrupted graph cache"
git push
# Render redeploys automatically
```

---

## Performance Validation

### Before & After Metrics

```bash
# Time startup
time python main.py
# Option 1 (runtime download): ~30-45s
# Option 2 (pickle cache): ~5-10s (+ 0.15s for graph load)

# Monitor memory
top -p $(pgrep -f main.py)
# Expect: ~500-800 MB RSS (includes graph + services)
```

### Load Test

```bash
# Use Apache Bench or wrk
ab -n 1000 -c 10 https://your-render-app.onrender.com/health

# Should see improved response times with graph pre-loaded
# Cache hit: route queries complete in < 50ms
```

---

## Troubleshooting

### Issue: "Graph cache not found" in production

**Cause**: Graph file not committed to git

**Solution**:
```bash
# Local
git add backend/data/osm_cache/dhaka_bangladesh_graph.pkl
git commit -m "fix: add missing graph cache"
git push

# Render redeploys automatically
```

### Issue: Startup hangs for 30+ seconds

**Cause**: Cache disabled or missing, falling back to OSM download

**Solution**:
```bash
# Check environment variable
echo $USE_GRAPH_CACHE  # Should be "1"

# If not set, update in Render dashboard
# Then redeploy
```

### Issue: "Pickle protocol version mismatch"

**Cause**: Cached pickle built with Python 3.10+, running on 3.9

**Solution**: Rebuild cache with target Python version:
```bash
# Ensure Python 3.11 is used
python --version
python build_graph_cache.py --force-download
```

---

## Cost Savings

### Compute (Render)

- **Before**: 30s startup × 10 deploys/day = 5 min wasted compute
- **After**: 5s startup × 10 deploys/day = 50 sec saved
- **ROI**: ~$1-2/month in startup time per instance

### Network

- **Before**: 15-30 MB OSM download per startup
- **After**: 0 MB (cache from git)
- **ROI**: $0-100/month if on metered bandwidth

### User Experience

- **Before**: 30-45s wait for first request
- **After**: < 100ms response time
- **Impact**: Users see instant map, faster feature adoption

---

## Next Steps

1. ✅ Build cache locally: `python build_graph_cache.py`
2. ✅ Commit to git: `git add backend/data/osm_cache/*.pkl`
3. ✅ Deploy: Push to main branch
4. ✅ Verify: Monitor startup logs for cache hit
5. 📊 Optional: Set up weekly cache rebuild via GitHub Actions
