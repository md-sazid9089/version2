/*
 * RouteSelectionPanel
 * ===================
 * Minimal left-side selector for two multimodal comparison routes.
 */

function formatDistance(meters) {
  if (!Number.isFinite(meters)) return '--';
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return '--';
  if (seconds >= 3600) {
    const h = Math.floor(seconds / 3600);
    const m = Math.round((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }
  if (seconds >= 60) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds)}s`;
}

function RouteOptionCard({
  title,
  color,
  route,
  isSelected,
  subtitle,
  onClick,
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: '100%',
        textAlign: 'left',
        padding: '12px 14px',
        borderRadius: 12,
        border: isSelected ? `1.5px solid ${color}` : '1px solid rgba(255,255,255,0.08)',
        background: isSelected ? 'rgba(255,255,255,0.07)' : 'rgba(255,255,255,0.03)',
        color: '#e5e7eb',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 800, color }}>{title}</span>
        {subtitle ? (
          <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 700 }}>{subtitle}</span>
        ) : null}
      </div>
      <div style={{ display: 'flex', gap: 12, fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}>
        <span>{formatDuration(route?.total_duration_s ?? route?.total_time ?? 0)}</span>
        <span>{formatDistance(route?.total_distance_m ?? route?.total_distance ?? 0)}</span>
      </div>
    </button>
  );
}

function RouteSelectionPanel({
  fastestRoute,
  shortestRoute,
  selectedRoute,
  onSelectRoute,
}) {
  if (!fastestRoute || !shortestRoute) {
    return null;
  }

  const slowerSeconds = Math.max(
    0,
    Number(shortestRoute.total_duration_s || shortestRoute.total_time || 0)
      - Number(fastestRoute.total_duration_s || fastestRoute.total_time || 0)
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <RouteOptionCard
        title="Fastest Route"
        color="#2563eb"
        route={fastestRoute}
        isSelected={selectedRoute === 'fastest'}
        onClick={() => onSelectRoute('fastest')}
      />
      <RouteOptionCard
        title="Shortest Route"
        color="#6b7280"
        route={shortestRoute}
        isSelected={selectedRoute === 'shortest'}
        subtitle={slowerSeconds > 0 ? `+${Math.round(slowerSeconds)}s slower` : null}
        onClick={() => onSelectRoute('shortest')}
      />
    </div>
  );
}

export default RouteSelectionPanel;
