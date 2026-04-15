/*
 * MapPage - Interactive Routing Map Interface
 * ==============================================
 * Full-screen map with floating HUD panels matching the design spec.
 */

import { useEffect, useMemo, useState } from 'react';
import MapView from '../components/MapView';
import RoutePanel from '../components/RoutePanel';
import ModeSelector from '../components/ModeSelector';
import AnomalyAlert from '../components/AnomalyAlert';
import AnomalyModal from '../components/AnomalyModal';
import RouteSelectionPanel from '../components/RouteSelectionPanel';
import { computeRoute, getRouteTraffic } from '../services/routeService';
import { getGraphSnapshot, reportAnomaly, getAnomalies, clearAnomalies } from '../services/api';

const VEHICLE_COLOR_LEGEND = [
  { label: 'Walking', color: '#8b5cf6' },
  { label: 'Rickshaw', color: '#22c55e' },
  { label: 'Bus', color: '#f59e0b' },
  { label: 'Car', color: '#ef4444' },
  { label: 'Bike', color: '#06b6d4' },
];

const isValidCoordinate = (lat, lng) => (
  Number.isFinite(lat)
  && Number.isFinite(lng)
  && Math.abs(lat) <= 90
  && Math.abs(lng) <= 180
);

const normalizeGeometry = (geometry) => {
  if (!Array.isArray(geometry)) return [];

  const normalized = geometry
    .map((point) => {
      if (Array.isArray(point) && point.length >= 2) {
        const lat = Number(point[0]);
        const lng = Number(point[1]);
        return isValidCoordinate(lat, lng) ? { lat, lng } : null;
      }

      const lat = Number(point?.lat);
      const lng = Number(point?.lng);
      return isValidCoordinate(lat, lng) ? { lat, lng } : null;
    })
    .filter(Boolean);

  const deduped = [];
  normalized.forEach((point) => {
    const prev = deduped[deduped.length - 1];
    if (!prev || prev.lat !== point.lat || prev.lng !== point.lng) {
      deduped.push(point);
    }
  });

  return deduped;
};

const normalizeComparisonRoute = (candidate) => {
  if (!candidate || typeof candidate !== 'object') return null;

  const rawSegments = Array.isArray(candidate.segments)
    ? candidate.segments
    : Array.isArray(candidate.legs)
      ? candidate.legs
      : [];

  const segments = rawSegments
    .map((segment) => {
      const geometry = normalizeGeometry(segment?.geometry || segment?.coordinates || []);
      if (geometry.length < 2) return null;

      return {
        mode: segment?.mode || segment?.recommended_vehicle || 'walk',
        geometry,
        distance_m: Number(segment?.distance_m ?? 0),
        duration_s: Number(segment?.duration_s ?? segment?.travel_time_s ?? 0),
      };
    })
    .filter(Boolean);

  if (segments.length === 0) {
    return null;
  }

  const fallbackDistance = segments.reduce((sum, segment) => sum + segment.distance_m, 0);
  const fallbackDuration = segments.reduce((sum, segment) => sum + segment.duration_s, 0);

  return {
    total_distance_m: Number(candidate.total_distance_m ?? candidate.total_distance ?? fallbackDistance),
    total_duration_s: Number(candidate.total_duration_s ?? candidate.total_time ?? fallbackDuration),
    segments,
  };
};

const extractComparisonRoutes = (routeResult) => {
  if (!routeResult) {
    return null;
  }

  const minTimeRoutes = Array.isArray(routeResult.min_time_routes) ? routeResult.min_time_routes : [];
  const minDistanceRoutes = Array.isArray(routeResult.min_distance_routes)
    ? routeResult.min_distance_routes
    : [];
  const suggestions = Array.isArray(routeResult.multimodal_suggestions)
    ? routeResult.multimodal_suggestions
    : [];

  const fastestSuggestions = suggestions.filter((item) => item?.strategy === 'fastest_time');
  const shortestSuggestions = suggestions.filter((item) => item?.strategy === 'shortest_distance');

  const fastest = normalizeComparisonRoute(
    minTimeRoutes[0] || fastestSuggestions[0] || suggestions[0] || null
  );
  const shortest = normalizeComparisonRoute(
    minDistanceRoutes[0] || shortestSuggestions[0] || suggestions[1] || suggestions[0] || null
  );

  if (!fastest && !shortest) {
    return null;
  }

  return {
    fastest: fastest || shortest,
    shortest: shortest || fastest,
  };
};

function MapPage({ apiStatus, onGoBack }) {
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [routeMode, setRouteMode] = useState('single');
  const [modes, setModes] = useState(['car']);
  const [routeResult, setRouteResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isAddingAnomaly, setIsAddingAnomaly] = useState(false);
  const [error, setError] = useState(null);
  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [anomalyModalOpen, setAnomalyModalOpen] = useState(false);
  const [selectedAnomalyEdgeId, setSelectedAnomalyEdgeId] = useState(null);
  const [anomalyTargetMode, setAnomalyTargetMode] = useState('edge');
  const [bboxStart, setBboxStart] = useState(null);
  const [selectedBBox, setSelectedBBox] = useState(null);
  const [isAnomalyPickMode, setIsAnomalyPickMode] = useState(false);
  const [isAnomalyPanelCollapsed, setIsAnomalyPanelCollapsed] = useState(true);
  const [lastRouteOptions, setLastRouteOptions] = useState({ includeMultimodal: false });
  const [selectedComparisonRoute, setSelectedComparisonRoute] = useState(null);

  const isBackendOnline =
    apiStatus?.status === 'healthy' ||
    apiStatus?.status === 'ok' ||
    apiStatus?.status === 'degraded';

  const comparisonRoutes = useMemo(() => extractComparisonRoutes(routeResult), [routeResult]);

  useEffect(() => {
    if (routeMode !== 'multimodal') {
      setSelectedComparisonRoute(null);
      return;
    }
    setSelectedComparisonRoute(null);
  }, [routeResult?.route_id, routeMode]);

  useEffect(() => {
    const routeId = routeResult?.route_id;
    const trafficStatus = routeResult?.traffic_status;
    if (!routeId || trafficStatus !== 'loading') {
      return undefined;
    }

    let canceled = false;
    let timerId = null;

    const pollTraffic = async () => {
      try {
        const payload = await getRouteTraffic(routeId);
        if (canceled) {
          return;
        }

        if (payload?.status === 'ready') {
          setRouteResult((prev) => {
            if (!prev || prev.route_id !== routeId) {
              return prev;
            }
            return {
              ...prev,
              traffic_status: 'ready',
              traffic_jam_prediction: payload?.data || null,
            };
          });
          return;
        }

        if (payload?.status === 'failed') {
          setRouteResult((prev) => {
            if (!prev || prev.route_id !== routeId) {
              return prev;
            }
            return {
              ...prev,
              traffic_status: 'failed',
            };
          });
          return;
        }
      } catch (_err) {
        // Keep polling for transient failures to preserve progressive loading UX.
      }

      if (!canceled) {
        timerId = setTimeout(pollTraffic, 1200);
      }
    };

    timerId = setTimeout(pollTraffic, 600);

    return () => {
      canceled = true;
      if (timerId) {
        clearTimeout(timerId);
      }
    };
  }, [routeResult?.route_id, routeResult?.traffic_status]);

  useEffect(() => {
    let isMounted = true;
    let anomalyTimerId = null;

    if (!isBackendOnline) {
      return () => {
        isMounted = false;
      };
    }

    const loadGraphNodes = async () => {
      try {
        // Load all nodes with accessibility info (don't filter server-side yet)
        const snapshot = await getGraphSnapshot(false);
        if (isMounted) {
          setGraphNodes(Array.isArray(snapshot?.nodes) ? snapshot.nodes : []);
        }
      } catch (err) {
        console.error('Failed to load graph nodes:', err);
      }
    };

    const loadGraphEdges = async () => {
      try {
        const snapshot = await getGraphSnapshot(true);
        if (isMounted) {
          setGraphEdges(Array.isArray(snapshot?.edges) ? snapshot.edges : []);
          if (!graphNodes.length && Array.isArray(snapshot?.nodes)) {
            setGraphNodes(snapshot.nodes);
          }
        }
      } catch (err) {
        console.error('Failed to load graph edges:', err);
      }
    };

    const fetchAnomalyState = async () => {
      try {
        const data = await getAnomalies();
        if (!isMounted) return;
        const list = Array.isArray(data?.anomalies) ? data.anomalies : [];
        setAnomalies(list);
        anomalyTimerId = setTimeout(fetchAnomalyState, 8000);
      } catch (err) {
        if (isMounted) {
          setAnomalies([]);
        }
        // Back off when backend is flaky/offline to reduce noisy retries.
        anomalyTimerId = setTimeout(fetchAnomalyState, 20000);
      }
    };

    loadGraphNodes();
    loadGraphEdges();
    fetchAnomalyState();

    return () => {
      isMounted = false;
      if (anomalyTimerId) {
        clearTimeout(anomalyTimerId);
      }
    };
  }, [isBackendOnline]);

  const nodeLookup = new Map(graphNodes.map((n) => [String(n.id), n]));

  const pointToSegmentDistanceSq = (p, a, b) => {
    const vx = b.lng - a.lng;
    const vy = b.lat - a.lat;
    const wx = p.lng - a.lng;
    const wy = p.lat - a.lat;
    const c1 = vx * wx + vy * wy;
    if (c1 <= 0) {
      const dx = p.lng - a.lng;
      const dy = p.lat - a.lat;
      return dx * dx + dy * dy;
    }
    const c2 = vx * vx + vy * vy;
    if (c2 <= c1) {
      const dx = p.lng - b.lng;
      const dy = p.lat - b.lat;
      return dx * dx + dy * dy;
    }
    const t = c1 / c2;
    const proj = { lng: a.lng + t * vx, lat: a.lat + t * vy };
    const dx = p.lng - proj.lng;
    const dy = p.lat - proj.lat;
    return dx * dx + dy * dy;
  };

  const findNearestEdgeId = (latlng) => {
    let bestEdgeId = null;
    let bestDist = Number.POSITIVE_INFINITY;

    graphEdges.forEach((edge) => {
      const sourceNode = nodeLookup.get(String(edge.source));
      const targetNode = nodeLookup.get(String(edge.target));
      if (!sourceNode || !targetNode) {
        return;
      }

      const d = pointToSegmentDistanceSq(
        { lat: latlng.lat, lng: latlng.lng },
        { lat: sourceNode.lat, lng: sourceNode.lng },
        { lat: targetNode.lat, lng: targetNode.lng }
      );
      if (d < bestDist) {
        bestDist = d;
        bestEdgeId = `${edge.source}->${edge.target}`;
      }
    });

    return bestEdgeId;
  };

  const handleMapClick = (latlng) => {
    if (isAnomalyPickMode) {
      if (anomalyTargetMode === 'edge') {
        const nearestEdgeId = findNearestEdgeId(latlng);
        if (!nearestEdgeId) {
          setError('Could not resolve nearest road segment for anomaly injection.');
          return;
        }
        setSelectedAnomalyEdgeId(nearestEdgeId);
        setSelectedBBox(null);
        setAnomalyModalOpen(true);
      } else {
        if (!bboxStart) {
          setBboxStart(latlng);
          setError('BBox start selected. Click second point to complete area.');
          return;
        }

        const south = Math.min(bboxStart.lat, latlng.lat);
        const west = Math.min(bboxStart.lng, latlng.lng);
        const north = Math.max(bboxStart.lat, latlng.lat);
        const east = Math.max(bboxStart.lng, latlng.lng);
        setSelectedBBox([south, west, north, east]);
        setBboxStart(null);
        setSelectedAnomalyEdgeId(null);
        setAnomalyModalOpen(true);
      }
      return;
    }

    if (!origin) {
      setOrigin(latlng);
    } else if (!destination) {
      setDestination(latlng);
    } else {
      setOrigin(latlng);
      setDestination(null);
      setRouteResult(null);
      setSelectedComparisonRoute(null);
      setError(null);
    }
  };

  const buildMultimodalModes = () => ['walk', 'transit', 'car', 'bike', 'rickshaw'];

  const handleComputeRoute = async (includeMultimodal = false) => {
    if (!isBackendOnline) {
      setError('Backend unavailable. Please ensure the server is running.');
      return;
    }

    if (!origin || !destination) {
      setError('Please set both origin and destination by clicking the map.');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      setLastRouteOptions({ includeMultimodal });
      const requestModes = includeMultimodal ? buildMultimodalModes() : [modes?.[0] || 'car'];
      const result = await computeRoute({
        origin,
        destination,
        modes: requestModes,
        optimize: 'time',
        avoid_anomalies: true,
        include_multimodal: includeMultimodal,
      });
      setRouteResult(result);
      setSelectedComparisonRoute(null);
    } catch (err) {
      setError(err.message || 'Failed to compute route');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAnomalySubmit = async ({ anomalyType, severity, vehicleTypes, startTime, endTime }) => {
    if (anomalyTargetMode === 'edge' && !selectedAnomalyEdgeId) {
      setError('Pick a road segment before applying anomaly.');
      return;
    }

    if (anomalyTargetMode === 'bbox' && !selectedBBox) {
      setError('Pick a bounding box before applying anomaly.');
      return;
    }

    setAnomalyModalOpen(false);
    setIsAddingAnomaly(true);
    setError(null);

    try {
      const payload = {
        type: anomalyType,
        severity,
        vehicle_types: vehicleTypes,
        start_time: startTime,
        end_time: endTime,
      };

      if (anomalyTargetMode === 'edge') {
        payload.edge_ids = [selectedAnomalyEdgeId];
        payload.target = { type: 'edge', edge_ids: [selectedAnomalyEdgeId] };
      } else {
        payload.target = { type: 'bbox', bbox: selectedBBox };
      }

      await reportAnomaly({
        ...payload,
        ttl: 300,
        description:
          anomalyTargetMode === 'edge'
            ? `Map anomaly (${anomalyType}) on edge ${selectedAnomalyEdgeId}`
            : `Map anomaly (${anomalyType}) on bbox ${selectedBBox?.join(',')}`,
      });

      const data = await getAnomalies();
      setAnomalies(Array.isArray(data?.anomalies) ? data.anomalies : []);

      if (origin && destination) {
        await handleComputeRoute(routeMode === 'multimodal');
      }
    } catch (err) {
      setError(err.message || 'Failed to apply anomaly');
    } finally {
      setIsAddingAnomaly(false);
    }
  };

  const handleClearAnomalies = async () => {
    try {
      await clearAnomalies();
      setAnomalies([]);
      setSelectedAnomalyEdgeId(null);
      setSelectedBBox(null);
      setBboxStart(null);
      if (origin && destination) {
        await handleComputeRoute(routeMode === 'multimodal');
      }
    } catch (err) {
      setError(err.message || 'Failed to clear anomalies');
    }
  };

  const anomalyEdgeIds = Array.from(
    new Set(
      anomalies.flatMap((a) => a.edge_ids || a.affected_edges || [])
    )
  );

  const handleClear = () => {
    setOrigin(null);
    setDestination(null);
    setRouteResult(null);
    setSelectedComparisonRoute(null);
    setError(null);
  };

  const handleOriginDrag = (latlng) => {
    setOrigin(latlng);
    setRouteResult(null);
    setSelectedComparisonRoute(null);
    setError(null);
  };

  const handleDestinationDrag = (latlng) => {
    setDestination(latlng);
    setRouteResult(null);
    setSelectedComparisonRoute(null);
    setError(null);
  };

  const handleRouteModeChange = (nextMode) => {
    setRouteMode(nextMode);
    setLastRouteOptions({ includeMultimodal: nextMode === 'multimodal' });
    setRouteResult(null);
    setSelectedComparisonRoute(null);
    setError(null);
  };

  const showMinimalComparisonPanel =
    routeMode === 'multimodal' && comparisonRoutes?.fastest && comparisonRoutes?.shortest;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 10,
      overflow: 'hidden',
      background: '#070709',
    }}>
      {/* Full-screen map */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <MapView
          origin={origin}
          destination={destination}
          routeResult={routeResult}
          comparisonRoutes={comparisonRoutes}
          selectedComparisonRoute={selectedComparisonRoute}
          onSelectComparisonRoute={setSelectedComparisonRoute}
          routeMode={routeMode}
          selectedMode={modes?.[0] || 'car'}
          graphNodes={graphNodes}
          graphEdges={graphEdges}
          anomalyEdgeIds={anomalyEdgeIds}
          anomalies={anomalies}
          selectedAnomalyEdgeId={selectedAnomalyEdgeId}
          selectedBBox={selectedBBox}
          bboxStart={bboxStart}
          onMapClick={handleMapClick}
          onOriginDrag={handleOriginDrag}
          onDestinationDrag={handleDestinationDrag}
        />
      </div>

      {/* Dark overlay for contrast */}
      <div style={{
        position: 'absolute',
        inset: 0,
        zIndex: 1,
        background: 'linear-gradient(135deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.15) 50%, rgba(0,0,0,0.35) 100%)',
        pointerEvents: 'none',
      }} />

      {/* Floating side panel */}
      <div className="hud-left-panel" style={{
        position: 'absolute',
        top: 10,
        left: 10,
        bottom: 10,
        width: 300,
        zIndex: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        overflowY: 'auto',
        overflowX: 'hidden',
        pointerEvents: 'auto',
        scrollbarWidth: 'none',
      }}>
        <button
          type="button"
          onClick={() => onGoBack && onGoBack()}
          style={{
            alignSelf: 'flex-start',
            padding: '9px 14px',
            borderRadius: 999,
            border: '1px solid rgba(255,255,255,0.14)',
            background: 'rgba(18,18,22,0.92)',
            color: '#e5e7eb',
            fontSize: 12,
            fontWeight: 700,
            cursor: 'pointer',
            boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
          }}
        >
          ← Go Back
        </button>

        {showMinimalComparisonPanel ? (
          <>
            <div style={{
              background: 'rgba(18,18,22,0.92)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderRadius: 22,
              padding: 16,
              border: '1px solid rgba(255,255,255,0.06)',
              boxShadow: '0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.03)',
            }}>
              <RouteSelectionPanel
                fastestRoute={comparisonRoutes.fastest}
                shortestRoute={comparisonRoutes.shortest}
                selectedRoute={selectedComparisonRoute}
                onSelectRoute={setSelectedComparisonRoute}
              />
            </div>

            <div style={{
              background: 'rgba(18,18,22,0.92)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderRadius: 22,
              padding: 16,
              border: '1px solid rgba(255,255,255,0.06)',
              boxShadow: '0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.03)',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}>
              <div style={{
                fontSize: 12,
                fontWeight: 800,
                letterSpacing: '0.02em',
                color: '#e5e7eb',
              }}>
                Vehicle Color Legend
              </div>

              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 8,
              }}>
                {VEHICLE_COLOR_LEGEND.map((item) => (
                  <div
                    key={item.label}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      color: '#cbd5e1',
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    <span style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: item.color,
                      boxShadow: `0 0 0 2px ${item.color}33`,
                      flexShrink: 0,
                    }} />
                    <span>{item.label}</span>
                  </div>
                ))}
              </div>

              <div style={{
                fontSize: 10,
                color: '#94a3b8',
                lineHeight: 1.4,
              }}>
                {selectedComparisonRoute
                  ? 'Vehicle colors are active on the selected route.'
                  : 'Select Fastest or Shortest to apply vehicle colors on map segments.'}
              </div>
            </div>
          </>
        ) : (
          <>
            {/* Transport Mode Card */}
            <div style={{
              background: 'rgba(18,18,22,0.92)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderRadius: 22,
              padding: 16,
              border: '1px solid rgba(255,255,255,0.06)',
              boxShadow: '0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.03)',
            }}>
              <ModeSelector
                selectedModes={modes}
                onChange={setModes}
                routeMode={routeMode}
                onRouteModeChange={handleRouteModeChange}
              />
            </div>

            {/* Route Planner Card */}
            <div style={{
              background: 'rgba(18,18,22,0.92)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderRadius: 22,
              padding: 16,
              border: '1px solid rgba(255,255,255,0.06)',
              boxShadow: '0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.03)',
            }}>
              <RoutePanel
                origin={origin}
                destination={destination}
                routeResult={routeResult}
                dualRoute={null}
                routeMode={routeMode}
                isLoading={isLoading}
                error={error}
                onCompute={() => handleComputeRoute(routeMode === 'multimodal')}
                onComputeMultimodal={() => handleComputeRoute(true)}
                onRouteModeChange={handleRouteModeChange}
                onClear={handleClear}
              />
            </div>

            {/* Anomaly Alert Card */}
            {anomalies.length > 0 && (
              <div style={{
                background: 'rgba(18,18,22,0.92)',
                backdropFilter: 'blur(24px)',
                WebkitBackdropFilter: 'blur(24px)',
                borderRadius: 22,
                padding: 16,
                border: '1px solid rgba(249,115,22,0.18)',
                boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
              }}>
                <AnomalyAlert anomalies={anomalies} />
              </div>
            )}
          </>
        )}
      </div>

      {/* Top-right anomaly controls */}
      <div className="hud-anomaly-controls" style={{
        position: 'absolute',
        top: 14,
        right: 14,
        width: 'min(320px, calc(100vw - 20px))',
        zIndex: 60,
        pointerEvents: 'auto',
      }}>
        {/* Always-visible launcher */}
        <button
          onClick={() => setIsAnomalyPanelCollapsed((v) => !v)}
          style={{
            width: isAnomalyPanelCollapsed ? 'auto' : '100%',
            marginBottom: 8,
            marginLeft: isAnomalyPanelCollapsed ? 'auto' : 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 14px',
            borderRadius: 999,
            border: '1px solid rgba(245,158,11,0.45)',
            background: 'linear-gradient(135deg, rgba(245,158,11,0.22), rgba(217,119,6,0.18))',
            color: '#fde68a',
            cursor: 'pointer',
            fontWeight: 800,
            fontSize: 13,
            fontFamily: 'Inter, system-ui, sans-serif',
            textAlign: 'left',
            boxShadow: '0 12px 32px rgba(0,0,0,0.55), 0 0 0 1px rgba(245,158,11,0.15)',
          }}
        >
          <span>{isAnomalyPanelCollapsed ? '⚠️' : '✕'}</span>
          <span>{isAnomalyPanelCollapsed ? 'Anomaly' : 'Close Anomaly Tools'}</span>
        </button>

        {!isAnomalyPanelCollapsed && (
        <div style={{
          background: 'rgba(18,18,22,0.92)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderRadius: 22,
          padding: 16,
          border: '1px solid rgba(249,115,22,0.18)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}>
          <div style={{ color: '#fbbf24', fontWeight: 800, fontSize: 13, fontFamily: 'Inter, system-ui, sans-serif' }}>
            Anomaly Injection
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => {
                setAnomalyTargetMode('edge');
                setBboxStart(null);
                setSelectedBBox(null);
              }}
              style={{
                flex: 1,
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid rgba(245,158,11,0.35)',
                background: anomalyTargetMode === 'edge' ? 'rgba(245,158,11,0.22)' : 'rgba(245,158,11,0.08)',
                color: '#fbbf24',
                cursor: 'pointer',
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              Edge
            </button>
            <button
              onClick={() => {
                setAnomalyTargetMode('bbox');
                setSelectedAnomalyEdgeId(null);
              }}
              style={{
                flex: 1,
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid rgba(245,158,11,0.35)',
                background: anomalyTargetMode === 'bbox' ? 'rgba(245,158,11,0.22)' : 'rgba(245,158,11,0.08)',
                color: '#fbbf24',
                cursor: 'pointer',
                fontWeight: 700,
                fontSize: 12,
              }}
            >
              BBox
            </button>
          </div>
          <button
            onClick={() => setIsAnomalyPickMode((v) => !v)}
            style={{
              padding: '10px 12px',
              borderRadius: 10,
              border: '1px solid rgba(245,158,11,0.35)',
              background: isAnomalyPickMode ? 'rgba(245,158,11,0.18)' : 'rgba(245,158,11,0.06)',
              color: '#fbbf24',
              cursor: 'pointer',
              fontWeight: 700,
            }}
          >
            {isAnomalyPickMode
              ? (anomalyTargetMode === 'edge'
                  ? 'Pick Active: Click Road Segment'
                  : 'Pick Active: Click 2 Points for BBox')
              : (anomalyTargetMode === 'edge'
                  ? 'Pick Road & Inject Anomaly'
                  : 'Pick BBox & Inject Anomaly')}
          </button>
          <button
            onClick={handleClearAnomalies}
            style={{
              padding: '10px 12px',
              borderRadius: 10,
              border: '1px solid rgba(239,68,68,0.35)',
              background: 'rgba(239,68,68,0.10)',
              color: '#f87171',
              cursor: 'pointer',
              fontWeight: 700,
            }}
          >
            Clear All Anomalies
          </button>
          {isAddingAnomaly && (
            <div style={{ color: '#f59e0b', fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}>
              Applying anomaly and recomputing route...
            </div>
          )}
          {anomalyEdgeIds.length > 0 && (
            <div style={{ color: '#ef4444', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}>
              Active affected edges: {anomalyEdgeIds.length}
            </div>
          )}
          {selectedBBox && (
            <div style={{ color: '#fbbf24', fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}>
              Selected BBox: {selectedBBox.map((v) => Number(v).toFixed(4)).join(', ')}
            </div>
          )}
        </div>
        )}
      </div>

      <AnomalyModal
        isOpen={anomalyModalOpen}
        onClose={() => setAnomalyModalOpen(false)}
        onSubmit={handleAnomalySubmit}
        target={
          anomalyTargetMode === 'edge'
            ? { type: 'edge', edgeId: selectedAnomalyEdgeId }
            : { type: 'bbox', bbox: selectedBBox }
        }
      />

      {/* Top-center instruction pill */}
      {!origin && (
        <div
          className="animate-fade-in"
          style={{
            position: 'absolute',
            top: 14,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 30,
            background: 'rgba(18,18,22,0.88)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 999,
            padding: '10px 24px',
            fontSize: 13,
            color: '#a3a3a3',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            fontFamily: 'Inter, system-ui, sans-serif',
          }}
        >
          Tap the map to set your <span style={{ color: '#22c55e', fontWeight: 700 }}>origin</span>
        </div>
      )}

      {origin && !destination && (
        <div
          className="animate-fade-in"
          style={{
            position: 'absolute',
            top: 14,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 30,
            background: 'rgba(18,18,22,0.88)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: 999,
            padding: '10px 24px',
            fontSize: 13,
            color: '#a3a3a3',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            fontFamily: 'Inter, system-ui, sans-serif',
          }}
        >
          Tap the map to set your <span style={{ color: '#8b5cf6', fontWeight: 700 }}>destination</span>
        </div>
      )}
    </div>
  );
}

export default MapPage;
