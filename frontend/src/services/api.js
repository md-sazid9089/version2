/*
 * Frontend — API Base Client
 * ============================
 * Centralized Axios instance for all API calls to the GoliTransit backend.
 *
 * Configuration:
 *   - Base URL from VITE_API_BASE_URL env var (default: http://localhost:8000)
 *   - In dev mode, Vite proxy rewrites /api → backend (see vite.config.js)
 *   - Axios interceptors for error handling and request logging
 *
 * Integration:
 *   - Imported by routeService.js and any other service modules
 *   - All API calls should go through this client for consistent config
 */

import axios from 'axios';

const NETWORK_ERROR_LOG_THROTTLE_MS = 5000;
let lastNetworkErrorLogAt = 0;

// ─── Base URL ───────────────────────────────────────────────────
// In dev: Use relative paths, Vite proxy handles routing to backend
// In prod: May need adjustment for deployed backend URL
const BASE_URL = '/api';

// ─── Axios Instance ─────────────────────────────────────────────

const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30000, // 30s timeout for routing computations
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Response Interceptor ───────────────────────────────────────

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error status
      const detail = error.response.data?.detail || error.message;
      console.error(`[API] ${error.response.status}: ${detail}`);
      return Promise.reject(new Error(detail));
    } else if (error.request) {
      // No response received
      const now = Date.now();
      if (now - lastNetworkErrorLogAt > NETWORK_ERROR_LOG_THROTTLE_MS) {
        console.error('[API] No response from server. Is the backend running?');
        lastNetworkErrorLogAt = now;
      }
      return Promise.reject(new Error('Backend unavailable. Please ensure the server is running.'));
    } else {
      console.error('[API] Request error:', error.message);
      return Promise.reject(error);
    }
  }
);


// ─── Exported API Methods ───────────────────────────────────────

/**
 * Health check — GET /health
 * Returns: { status, service, version, graph: { loaded, nodes, edges } }
 */
export async function checkHealth() {
  const response = await apiClient.get('/health');
  return response.data;
}

/**
 * Get graph snapshot — GET /graph/snapshot
 * @param {boolean} includeEdges - Whether to include full edge list
 * @param {string} bbox - Bounding box filter "south,west,north,east"
 */
export async function getGraphSnapshot(includeEdges = false, bbox = null) {
  const params = { include_edges: includeEdges };
  if (bbox) params.bbox = bbox;
  const response = await apiClient.get('/graph/snapshot', { params });
  return response.data;
}

/**
 * List active anomalies — GET /anomaly
 * Returns: { anomalies: [...], count: number }
 */
export async function getAnomalies() {
  const response = await apiClient.get('/anomaly');
  return response.data;
}

/**
 * Report an anomaly — POST /anomaly
 * @param {object} report - AnomalyReport object
 */
export async function reportAnomaly(report) {
  const response = await apiClient.post('/anomaly', report);
  return response.data;
}

export async function clearAnomalies() {
  const response = await apiClient.delete('/anomaly');
  return response.data;
}

export default apiClient;
