/*
 * Frontend — Route Service
 * ==========================
 * Route-specific API calls to the GoliTransit backend.
 *
 * Integration:
 *   - Uses the base API client from api.js
 *   - Called by MapPage.jsx to compute routes
 *   - Request/response shapes match backend models/route_models.py
 */

import apiClient from './api';

/**
 * Compute a route — POST /route
 *
 * @param {object} params
 * @param {object} params.origin - { lat, lng }
 * @param {object} params.destination - { lat, lng }
 * @param {string[]} params.modes - Transport mode sequence, e.g. ["car"] or ["walk", "transit", "walk"]
 * @param {string} params.optimize - Optimization criterion: "time" | "distance" | "cost"
 * @param {boolean} params.avoid_anomalies - Whether to avoid anomaly-affected edges
 * @param {number} [params.max_alternatives] - Number of alternatives to request
 *
 * @returns {Promise<object>} RouteResponse:
 *   {
 *     legs: [{ mode, geometry, distance_m, duration_s, cost, instructions }],
 *     mode_switches: [{ from_mode, to_mode, location, penalty_time_s, penalty_cost }],
 *     total_distance_m, total_duration_s, total_cost,
 *     anomalies_avoided,
 *     alternatives: [[legs...], ...]
 *   }
 */
export async function computeRoute({
  origin,
  destination,
  modes = ['car'],
  optimize = 'time',
  avoid_anomalies = true,
  max_alternatives = null,
  include_multimodal = false,
  traffic_hour_of_day = new Date().getHours(),
}) {
  const payload = {
    origin: { lat: origin.lat, lng: origin.lng },
    destination: { lat: destination.lat, lng: destination.lng },
    modes,
    optimize,
    avoid_anomalies,
    include_multimodal,
    traffic_hour_of_day,
  };

  if (max_alternatives !== null) {
    payload.max_alternatives = max_alternatives;
  }

  const response = await apiClient.post('/route', payload);
  return response.data;
}

/**
 * Poll asynchronous traffic prediction for an existing route.
 *
 * @param {string} routeId
 * @returns {Promise<{route_id:string,status:string,data?:object,error?:string}>}
 */
export async function getRouteTraffic(routeId) {
  const response = await apiClient.get(`/traffic/${encodeURIComponent(routeId)}`);
  return response.data;
}

/**
 * Compute route with demo scenario — applies preset anomalies then routes.
 *
 * @param {string} scenarioKey - Key from config.json demo_scenarios
 * @param {object} routeParams - Same as computeRoute params
 */
export async function computeRouteWithScenario(scenarioKey, routeParams) {
  // TODO: Implement demo scenario flow:
  // 1. Fetch scenario anomalies from config
  // 2. POST each anomaly via /anomaly
  // 3. Compute route with avoid_anomalies=true
  // For now, just compute normally
  return computeRoute(routeParams);
}
