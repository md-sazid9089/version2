/*
 * MapView - Leaflet Map Wrapper Component
 * ==========================================
 * Renders map, markers, and backend-provided route geometry.
 */

import { createPortal } from 'react-dom';
import { useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, Popup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';

const ROUTE_VIEW_COLORS = {
  fastest: '#2563eb',
  shortest: '#6b7280',
  overlap: '#4b5563',
};

const VEHICLE_MODE_COLORS = {
  walk: '#8b5cf6',
  rickshaw: '#22c55e',
  transit: '#f59e0b',
  bus: '#f59e0b',
  car: '#ef4444',
  bike: '#06b6d4',
};

const SINGLE_MODE_COLORS = {
  car: '#3b82f6',
  bike: '#22c55e',
  rickshaw: '#f97316',
  walk: '#9ca3af',
  bus: '#ef4444',
  transit: '#ef4444',
};

const MODE_NODE_COLORS = {
  car: '#ef4444',
  bike: '#22c55e',
  walk: '#f97316',
  transit: '#3b82f6',
  rickshaw: '#facc15',
};

const originIcon = new L.DivIcon({
  className: '',
  html: `<div style="
    width: 20px; height: 20px; border-radius: 50%;
    background: #22c55e;
    border: 3px solid #ffffff;
    box-shadow: 0 0 0 4px rgba(34,197,94,0.30), 0 4px 12px rgba(0,0,0,0.5);
  "></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

const destIcon = new L.DivIcon({
  className: '',
  html: `<div style="
    width: 20px; height: 20px; border-radius: 50%;
    background: #8b5cf6;
    border: 3px solid #ffffff;
    box-shadow: 0 0 0 4px rgba(139,92,246,0.30), 0 4px 12px rgba(0,0,0,0.5);
  "></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

const isValidCoordinate = (lat, lng) => (
  Number.isFinite(lat)
  && Number.isFinite(lng)
  && Math.abs(lat) <= 90
  && Math.abs(lng) <= 180
);

const toPointPair = (point) => {
  if (Array.isArray(point) && point.length >= 2) {
    const lat = Number(point[0]);
    const lng = Number(point[1]);
    return isValidCoordinate(lat, lng) ? [lat, lng] : null;
  }

  const lat = Number(point?.lat);
  const lng = Number(point?.lng);
  return isValidCoordinate(lat, lng) ? [lat, lng] : null;
};

const sanitizePositions = (geometry) => {
  if (!Array.isArray(geometry)) {
    return [];
  }

  const normalized = geometry
    .map(toPointPair)
    .filter(Boolean);

  const deduped = [];
  normalized.forEach((point) => {
    const prev = deduped[deduped.length - 1];
    if (!prev || prev[0] !== point[0] || prev[1] !== point[1]) {
      deduped.push(point);
    }
  });

  return deduped;
};

const haversineMeters = (a, b) => {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const earthRadiusM = 6371000;
  const dLat = toRad(b[0] - a[0]);
  const dLng = toRad(b[1] - a[1]);
  const lat1 = toRad(a[0]);
  const lat2 = toRad(b[0]);

  const x = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  const y = 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));

  return earthRadiusM * y;
};

const edgeKey = (from, to) => {
  const fmt = ([lat, lng]) => `${lat.toFixed(6)},${lng.toFixed(6)}`;
  const a = fmt(from);
  const b = fmt(to);
  return a < b ? `${a}|${b}` : `${b}|${a}`;
};

const buildRouteRenderData = (route, routeKey) => {
  if (!route || !Array.isArray(route.segments)) {
    return null;
  }

  const orderedEdges = [];
  const segmentPolylines = [];
  let previousEnd = null;

  for (let i = 0; i < route.segments.length; i += 1) {
    const segment = route.segments[i];
    const positions = sanitizePositions(segment?.geometry);

    if (positions.length < 2) {
      continue;
    }

    if (previousEnd && haversineMeters(previousEnd, positions[0]) > 5000) {
      console.error(`[MapView] ${routeKey} route continuity check failed between segments.`);
      return null;
    }

    for (let j = 1; j < positions.length; j += 1) {
      const from = positions[j - 1];
      const to = positions[j];

      if (haversineMeters(from, to) > 15000) {
        console.error(`[MapView] ${routeKey} route continuity check failed inside segment ${i}.`);
        return null;
      }

      orderedEdges.push({
        key: edgeKey(from, to),
        from,
        to,
      });
    }

    segmentPolylines.push({
      key: `${routeKey}-segment-${i}`,
      mode: segment?.mode || 'walk',
      positions,
    });

    previousEnd = positions[positions.length - 1];
  }

  if (!orderedEdges.length) {
    console.error(`[MapView] ${routeKey} route has no valid coordinates for rendering.`);
    return null;
  }

  return { orderedEdges, segmentPolylines };
};

const buildInitialComparisonPolylines = (fastestData, shortestData) => {
  const fastestKeys = new Set(fastestData.orderedEdges.map((edge) => edge.key));
  const shortestKeys = new Set(shortestData.orderedEdges.map((edge) => edge.key));
  const shared = new Set(
    Array.from(fastestKeys).filter((key) => shortestKeys.has(key))
  );

  const buildChunks = (routeKey, routeData, includeShared) => {
    const chunks = [];
    let current = null;

    routeData.orderedEdges.forEach((edge, index) => {
      const isShared = shared.has(edge.key);
      if (isShared && !includeShared) {
        if (current) {
          chunks.push(current);
          current = null;
        }
        return;
      }

      const chunkType = isShared ? 'overlap' : routeKey;
      const color = isShared
        ? ROUTE_VIEW_COLORS.overlap
        : routeKey === 'fastest'
          ? ROUTE_VIEW_COLORS.fastest
          : ROUTE_VIEW_COLORS.shortest;

      if (!current || current.type !== chunkType) {
        if (current) {
          chunks.push(current);
        }

        current = {
          key: `${routeKey}-${chunkType}-${index}`,
          routeKey,
          type: chunkType,
          color,
          clickable: !isShared,
          positions: [edge.from, edge.to],
        };
      } else {
        current.positions.push(edge.to);
      }
    });

    if (current) {
      chunks.push(current);
    }

    return chunks;
  };

  return [
    ...buildChunks('fastest', fastestData, true),
    ...buildChunks('shortest', shortestData, false),
  ];
};

function MapClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

function MapFABControls() {
  const map = useMap();
  const container = map.getContainer();

  const fabBase = {
    width: 48,
    height: 48,
    borderRadius: '50%',
    background: '#8b5cf6',
    color: '#ffffff',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 20,
    fontWeight: 700,
    boxShadow: '0 8px 24px rgba(0,0,0,0.55)',
    transition: 'transform 0.18s ease, filter 0.18s ease',
    outline: 'none',
    userSelect: 'none',
  };

  const onEnter = (e) => {
    e.currentTarget.style.transform = 'scale(1.08)';
    e.currentTarget.style.filter = 'brightness(1.15)';
  };

  const onLeave = (e) => {
    e.currentTarget.style.transform = 'scale(1)';
    e.currentTarget.style.filter = 'brightness(1)';
  };

  return createPortal(
    <div
      style={{
        position: 'absolute',
        right: 20,
        bottom: 100,
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        pointerEvents: 'all',
      }}
    >
      <button
        style={fabBase}
        onClick={() => map.zoomIn()}
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
        title="Zoom In"
      >
        +
      </button>

      <button
        style={fabBase}
        onClick={() => map.zoomOut()}
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
        title="Zoom Out"
      >
        -
      </button>
    </div>,
    container
  );
}

function MapView({
  origin,
  destination,
  routeResult,
  comparisonRoutes,
  selectedComparisonRoute,
  onSelectComparisonRoute,
  routeMode,
  selectedMode,
  graphNodes,
  graphEdges,
  anomalyEdgeIds,
  anomalies,
  selectedAnomalyEdgeId,
  selectedBBox,
  bboxStart,
  onMapClick,
  onOriginDrag,
  onDestinationDrag,
}) {
  const defaultCenter = [23.7639, 90.4066];
  const defaultZoom = 14;

  const singleModeLineColor = SINGLE_MODE_COLORS[selectedMode] || '#22c55e';

  const comparisonRenderData = useMemo(() => {
    if (routeMode !== 'multimodal' || !comparisonRoutes?.fastest || !comparisonRoutes?.shortest) {
      return null;
    }

    const fastest = buildRouteRenderData(comparisonRoutes.fastest, 'fastest');
    const shortest = buildRouteRenderData(comparisonRoutes.shortest, 'shortest');

    if (!fastest || !shortest) {
      return null;
    }

    return {
      fastest,
      shortest,
      initialPolylines: buildInitialComparisonPolylines(fastest, shortest),
    };
  }, [routeMode, comparisonRoutes]);

  const selectedVehiclePolylines = useMemo(() => {
    if (!comparisonRenderData || !selectedComparisonRoute) {
      return [];
    }

    const selected = selectedComparisonRoute === 'shortest'
      ? comparisonRenderData.shortest
      : comparisonRenderData.fastest;

    return selected.segmentPolylines.map((segment) => ({
      key: segment.key,
      color: VEHICLE_MODE_COLORS[segment.mode] || '#38bdf8',
      positions: segment.positions,
    }));
  }, [comparisonRenderData, selectedComparisonRoute]);

  const singleModeRoutePositions = useMemo(() => {
    const legs = Array.isArray(routeResult?.legs) ? routeResult.legs : [];
    const positions = legs.flatMap((leg) => sanitizePositions(leg?.geometry || []));
    return positions;
  }, [routeResult]);

  const originDragHandlers = useMemo(
    () => ({
      dragend(e) {
        const latlng = e.target.getLatLng();
        if (onOriginDrag) {
          onOriginDrag({ lat: latlng.lat, lng: latlng.lng });
        }
      },
    }),
    [onOriginDrag]
  );

  const destinationDragHandlers = useMemo(
    () => ({
      dragend(e) {
        const latlng = e.target.getLatLng();
        if (onDestinationDrag) {
          onDestinationDrag({ lat: latlng.lat, lng: latlng.lng });
        }
      },
    }),
    [onDestinationDrag]
  );

  const filteredNodes = useMemo(() => {
    if (!Array.isArray(graphNodes)) return [];

    if (routeMode === 'multimodal') {
      return graphNodes.map((node) => ({
        ...node,
        position: [node.lat, node.lng],
        color: '#3b82f6',
        opacity: 0.78,
      }));
    }

    return graphNodes
      .filter((node) => node.accessible_modes && node.accessible_modes.includes(selectedMode))
      .map((node) => ({
        ...node,
        position: [node.lat, node.lng],
        color: MODE_NODE_COLORS[selectedMode] || '#60a5fa',
        opacity: Math.min(0.9, 0.5 + (node.accessible_modes.length * 0.1)),
      }));
  }, [graphNodes, selectedMode, routeMode]);

  const nodeLookup = useMemo(() => {
    const map = new Map();
    (graphNodes || []).forEach((node) => map.set(String(node.id), node));
    return map;
  }, [graphNodes]);

  const anomalyPolylines = useMemo(() => {
    if (!Array.isArray(graphEdges) || graphEdges.length === 0) {
      return [];
    }

    const affected = new Set(anomalyEdgeIds || []);
    const highlighted = [];

    const anomalyByEdge = new Map();
    (anomalies || []).forEach((anomaly) => {
      (anomaly.edge_ids || anomaly.affected_edges || []).forEach((edgeIdValue) => {
        if (!anomalyByEdge.has(edgeIdValue)) {
          anomalyByEdge.set(edgeIdValue, []);
        }
        anomalyByEdge.get(edgeIdValue).push(anomaly);
      });
    });

    graphEdges.forEach((edge, idx) => {
      const edgeIdValue = `${edge.source}->${edge.target}`;
      if (!affected.has(edgeIdValue) && edgeIdValue !== selectedAnomalyEdgeId) {
        return;
      }

      let positions = sanitizePositions(edge.geometry || []);
      if (positions.length < 2) {
        const src = nodeLookup.get(String(edge.source));
        const dst = nodeLookup.get(String(edge.target));
        if (!src || !dst) {
          return;
        }
        positions = [[src.lat, src.lng], [dst.lat, dst.lng]];
      }

      highlighted.push({
        key: `anomaly-edge-${idx}`,
        positions,
        selected: edgeIdValue === selectedAnomalyEdgeId,
        edgeId: edgeIdValue,
        anomalies: anomalyByEdge.get(edgeIdValue) || [],
      });
    });

    return highlighted;
  }, [graphEdges, anomalyEdgeIds, selectedAnomalyEdgeId, nodeLookup, anomalies]);

  const bboxPolyline = useMemo(() => {
    if (!selectedBBox || selectedBBox.length !== 4) {
      return null;
    }
    const [south, west, north, east] = selectedBBox;
    return [
      [south, west],
      [south, east],
      [north, east],
      [north, west],
      [south, west],
    ];
  }, [selectedBBox]);

  return (
    <MapContainer
      center={defaultCenter}
      zoom={defaultZoom}
      style={{ width: '100%', height: '100%' }}
      zoomControl={false}
      preferCanvas={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      <MapClickHandler onMapClick={onMapClick} />
      <MapFABControls />

      {origin && (
        <Marker position={[origin.lat, origin.lng]} icon={originIcon} draggable eventHandlers={originDragHandlers}>
          <Popup>
            <span style={{ color: '#22c55e', fontWeight: 600 }}>Origin</span>
            <br />
            {origin.lat.toFixed(5)}, {origin.lng.toFixed(5)}
            <br />
            Drag to update
          </Popup>
        </Marker>
      )}

      {destination && (
        <Marker
          position={[destination.lat, destination.lng]}
          icon={destIcon}
          draggable
          eventHandlers={destinationDragHandlers}
        >
          <Popup>
            <span style={{ color: '#8b5cf6', fontWeight: 600 }}>Destination</span>
            <br />
            {destination.lat.toFixed(5)}, {destination.lng.toFixed(5)}
            <br />
            Drag to update
          </Popup>
        </Marker>
      )}

      {routeMode === 'multimodal' && comparisonRenderData ? (
        selectedComparisonRoute ? (
          selectedVehiclePolylines.map((polyline) => (
            <Polyline
              key={polyline.key}
              positions={polyline.positions}
              pathOptions={{
                color: polyline.color,
                weight: 6,
                opacity: 0.95,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          ))
        ) : (
          comparisonRenderData.initialPolylines.map((polyline) => (
            <Polyline
              key={polyline.key}
              positions={polyline.positions}
              pathOptions={{
                color: polyline.color,
                weight: polyline.type === 'overlap' ? 7 : 6,
                opacity: 0.92,
                lineCap: 'round',
                lineJoin: 'round',
              }}
              eventHandlers={polyline.clickable ? {
                click: () => {
                  if (onSelectComparisonRoute) {
                    onSelectComparisonRoute(polyline.routeKey);
                  }
                },
              } : undefined}
            />
          ))
        )
      ) : (
        singleModeRoutePositions.length >= 2 && (
          <Polyline
            positions={singleModeRoutePositions}
            pathOptions={{
              color: singleModeLineColor,
              weight: 5,
              opacity: 0.9,
              lineCap: 'round',
              lineJoin: 'round',
            }}
          />
        )
      )}

      {anomalyPolylines.map((line) => (
        <Polyline
          key={line.key}
          positions={line.positions}
          pathOptions={{
            color: line.selected ? '#f97316' : '#ef4444',
            weight: line.selected ? 7 : 5,
            opacity: line.selected ? 0.95 : 0.75,
            lineCap: 'round',
            lineJoin: 'round',
            dashArray: line.selected ? null : '8 6',
          }}
        >
          <Popup>
            <div style={{ minWidth: 200 }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>Affected Edge</div>
              <div style={{ fontSize: 12, marginBottom: 6 }}>{line.edgeId}</div>
              {line.anomalies.slice(0, 3).map((anomaly) => (
                <div key={anomaly.anomaly_id} style={{ fontSize: 12, marginBottom: 4 }}>
                  {anomaly.type}: x{Number(anomaly.severity || anomaly.weight_multiplier || 1).toFixed(1)}
                </div>
              ))}
            </div>
          </Popup>
        </Polyline>
      ))}

      {bboxPolyline && (
        <Polyline
          positions={bboxPolyline}
          pathOptions={{
            color: '#f59e0b',
            weight: 3,
            opacity: 0.9,
            dashArray: '8 6',
          }}
        />
      )}

      {bboxStart && (
        <CircleMarker
          center={[bboxStart.lat, bboxStart.lng]}
          radius={6}
          pathOptions={{
            color: '#f59e0b',
            weight: 2,
            fillColor: '#fbbf24',
            fillOpacity: 0.9,
          }}
        />
      )}

      {filteredNodes.map((node, idx) => (
        <CircleMarker
          key={`graph-node-${node.id}-${idx}`}
          center={node.position}
          radius={2.2}
          pathOptions={{
            color: node.color,
            weight: 1.5,
            fillColor: node.color,
            fillOpacity: node.opacity,
          }}
        >
          <Popup>
            <div style={{ fontSize: 12, fontFamily: 'monospace' }}>
              <div style={{ fontWeight: 700, marginBottom: 4, color: node.color }}>
                Node {node.id}
              </div>
              <div style={{ fontSize: 11, marginBottom: 2 }}>
                {node.lat.toFixed(5)}, {node.lng.toFixed(5)}
              </div>
              <div style={{ fontSize: 10, color: '#999', marginTop: 4 }}>
                Accessible to:
              </div>
              <div style={{ fontSize: 10, marginTop: 2 }}>
                {node.accessible_modes?.length > 0 ? (
                  node.accessible_modes.map((mode) => (
                    <div key={mode} style={{ color: MODE_NODE_COLORS[mode] }}>
                      • {mode}
                    </div>
                  ))
                ) : (
                  <span style={{ color: '#666' }}>No modes</span>
                )}
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

export default MapView;
