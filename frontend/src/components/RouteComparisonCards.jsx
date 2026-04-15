/*
 * RouteComparisonCards — Dual Route Comparison Display
 * ===================================================== 
 * Shows both min_time and min_distance routes side-by-side
 * with interactive switching and smart insights
 */

import { useMemo } from 'react';

function RouteComparisonCards({ 
  dualRoute, 
  routeMode, 
  onRouteModeChange,
  hoveredRoute,
  onRouteHover 
}) {
  const { min_time_route, min_distance_route } = dualRoute || {};

  // Check if routes are effectively identical
  const areRoutesIdentical = useMemo(() => {
    if (!min_time_route || !min_distance_route) return false;

    const timeDistance = Number(min_time_route.total_distance ?? min_time_route.total_distance_m ?? 0);
    const distanceDistance = Number(min_distance_route.total_distance ?? min_distance_route.total_distance_m ?? 0);
    const timeDiff = Math.abs(timeDistance - distanceDistance);
    const distSimilarity = timeDiff / Math.max(timeDistance, distanceDistance, 1);
    
    // Consider identical if within 5% difference
    return distSimilarity < 0.05;
  }, [min_time_route, min_distance_route]);

  // Compute comparison insights
  const insights = useMemo(() => {
    if (!min_time_route || !min_distance_route) return null;

    const timeTime = Number(min_time_route.total_time ?? min_time_route.total_duration_s ?? 0);
    const distanceTime = Number(min_distance_route.total_time ?? min_distance_route.total_duration_s ?? 0);
    const timeDistance = Number(min_time_route.total_distance ?? min_time_route.total_distance_m ?? 0);
    const distanceDistance = Number(min_distance_route.total_distance ?? min_distance_route.total_distance_m ?? 0);

    const timeDiff = timeTime - distanceTime;
    const distDiff = distanceDistance - timeDistance;
    
    return {
      timeDiff: Math.abs(timeDiff),
      timeFaster: timeDiff > 0 ? 'distance' : 'time', // Which is faster
      distDiff: Math.abs(distDiff),
      distShorter: distDiff > 0 ? 'time' : 'distance', // Which is shorter
    };
  }, [min_time_route, min_distance_route]);

  if (!min_time_route || !min_distance_route) {
    return null;
  }

  if (areRoutesIdentical) {
    // Show single unified card
    return (
      <div className="animate-slide-up" style={{
        padding: '16px',
        background: 'rgba(34, 197, 94, 0.08)',
        border: '1.5px solid rgba(34, 197, 94, 0.25)',
        borderRadius: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          justifyContent: 'space-between',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <span style={{ fontSize: 20 }}>🏆</span>
            <div>
              <div style={{
                fontSize: 12,
                fontWeight: 800,
                color: '#22c55e',
                letterSpacing: '-0.01em',
              }}>
                Fastest & Shortest Route
              </div>
              <div style={{
                fontSize: 9,
                color: '#525252',
                fontFamily: 'JetBrains Mono, monospace',
              }}>
                Optimal route for all metrics
              </div>
            </div>
          </div>
        </div>

        <div style={{
          display: 'flex',
          gap: 12,
          fontSize: 12,
          fontWeight: 600,
          fontFamily: 'JetBrains Mono, monospace',
        }}>
          <span style={{ color: '#a3a3a3' }}>
            {formatDistance(Number(min_time_route.total_distance ?? min_time_route.total_distance_m ?? 0))}
          </span>
          <span style={{ color: '#a3a3a3' }}>
            {formatDuration(Number(min_time_route.total_time ?? min_time_route.total_duration_s ?? 0))}
          </span>
        </div>
      </div>
    );
  }

  // Show dual comparison cards
  const isTimeSelected = routeMode === 'min_time';
  const isDistanceSelected = routeMode === 'min_distance';

  return (
    <div className="animate-slide-up" style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      {/* Comparison Header */}
      <div style={{
        padding: '12px 14px',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        borderRadius: 12,
        fontSize: 10,
        color: '#737373',
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <span>💡</span>
        <span>
          {insights.timeFaster === 'time'
            ? `⏱️ Fastest saves ${formatDuration(insights.timeDiff)}`
            : `📍 Shortest saves ${formatDistance(insights.distDiff)}`}
        </span>
      </div>

      {/* Blue: Fastest Route Card */}
      <RouteComparisonCard
        title="Fastest Route"
        icon="🟣"
        color="#6d28d9"
        route={min_time_route}
        isSelected={isTimeSelected}
        isHovered={hoveredRoute === 'min_time'}
        onClick={() => onRouteModeChange('min_time')}
        onHover={(hovered) => onRouteHover(hovered ? 'min_time' : null)}
        advantage={
          insights.timeFaster === 'time'
            ? `${formatDuration(insights.timeDiff)} quicker`
            : null
        }
      />

      {/* Green: Shortest Route Card */}
      <RouteComparisonCard
        title="Shortest Route"
        icon="💗"
        color="#db2777"
        route={min_distance_route}
        isSelected={isDistanceSelected}
        isHovered={hoveredRoute === 'min_distance'}
        onClick={() => onRouteModeChange('min_distance')}
        onHover={(hovered) => onRouteHover(hovered ? 'min_distance' : null)}
        advantage={
          insights.distShorter === 'distance'
            ? `${formatDistance(insights.distDiff)} shorter`
            : null
        }
      />
    </div>
  );
}

function RouteComparisonCard({
  title,
  icon,
  color,
  route,
  isSelected,
  isHovered,
  onClick,
  onHover,
  advantage,
}) {
  const opacity = isSelected ? 1 : isHovered ? 0.8 : 0.7;

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      style={{
        padding: '14px',
        background: isSelected
          ? `${color}15`
          : 'rgba(255, 255, 255, 0.02)',
        border: isSelected
          ? `1.5px solid ${color}40`
          : '1px solid rgba(255, 255, 255, 0.05)',
        borderRadius: 14,
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        opacity: opacity,
        transform: isHovered ? 'translateY(-2px)' : 'none',
        boxShadow: isHovered
          ? `0 8px 16px rgba(0, 0, 0, 0.3), 0 0 0 1px ${color}30`
          : 'none',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <span style={{ fontSize: 16 }}>{icon}</span>
          <div styles={{
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{
              fontSize: 11,
              fontWeight: 800,
              color: color,
              letterSpacing: '-0.01em',
              textTransform: 'uppercase',
            }}>
              {title}
            </div>
            {advantage && (
              <div style={{
                fontSize: 8,
                color: '#737373',
                fontFamily: 'JetBrains Mono, monospace',
              }}>
                {advantage}
              </div>
            )}
          </div>
        </div>
        {isSelected && (
          <span style={{
            fontSize: 14,
            color: color,
          }}>
            {'\u2714'}
          </span>
        )}
      </div>

      {/* Metrics */}
      <div style={{
        display: 'flex',
        gap: 12,
        fontSize: 12,
        fontWeight: 700,
        fontFamily: 'JetBrains Mono, monospace',
      }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}>
          <div style={{ color: color, fontSize: 13 }}>
            {formatDistance(Number(route.total_distance ?? route.total_distance_m ?? 0))}
          </div>
          <div style={{
            fontSize: 8,
            color: '#525252',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}>
            Distance
          </div>
        </div>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}>
          <div style={{ color: color, fontSize: 13 }}>
            {formatDuration(Number(route.total_time ?? route.total_duration_s ?? 0))}
          </div>
          <div style={{
            fontSize: 8,
            color: '#525252',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}>
            Time
          </div>
        </div>
      </div>

      {/* Mode breakdown */}
      {route.segments && route.segments.length > 0 && (
        <div style={{
          fontSize: 9,
          color: '#737373',
          fontFamily: 'JetBrains Mono, monospace',
          display: 'flex',
          gap: 6,
          flexWrap: 'wrap',
        }}>
          {getModeSequence(route.segments).map((mode, idx) => (
            <span key={idx} style={{
              background: 'rgba(255, 255, 255, 0.05)',
              padding: '2px 8px',
              borderRadius: 4,
              whiteSpace: 'nowrap',
            }}>
              {getModeEmoji(mode)} {getModeLabel(mode)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Helpers ---

function getModeSequence(segments) {
  if (!Array.isArray(segments)) return [];
  const unique = [];
  let lastMode = null;
  for (const seg of segments) {
    const mode = seg.mode || seg.recommended_vehicle;
    if (mode !== lastMode) {
      unique.push(mode);
      lastMode = mode;
    }
  }
  return unique;
}

function getModeEmoji(mode) {
  return ({
    car: '🚗',
    bike: '🚲',
    walk: '🚶',
    transit: '🚌',
    bus: '🚌',
    rickshaw: '🛺',
  })[mode] || '📍';
}

function getModeLabel(mode) {
  return ({
    car: 'Car',
    bike: 'Bike',
    walk: 'Walk',
    transit: 'Bus',
    bus: 'Bus',
    rickshaw: 'Rickshaw',
  })[mode] || mode;
}

function formatDistance(meters) {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function formatDuration(seconds) {
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }
  if (seconds >= 60) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds)}s`;
}

export default RouteComparisonCards;
