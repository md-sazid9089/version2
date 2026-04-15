/*
 * AnomalyAlert — Real-Time Anomaly Notification Component
 * ==========================================================
 * Shows active traffic anomalies affecting the routing area.
 *
 * Display:
 *   - Color-coded severity badges (low=blue, medium=yellow, high=orange, critical=red)
 *   - Anomaly type icon and description
 *   - Countdown timer to expiry
 *
 * Integration:
 *   - Receives anomaly list from MapPage state
 *   - Anomalies come from GET /anomaly API via routeService
 *   - Can be polled on an interval for real-time updates
 */

function AnomalyAlert({ anomalies }) {
  if (!anomalies || anomalies.length === 0) return null;

  return (
    <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* Console header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '7px 12px',
        background: 'rgba(245,158,11,0.09)',
        border: '1px solid rgba(245,158,11,0.22)',
        borderRadius: 12,
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: '#f59e0b',
          boxShadow: '0 0 8px rgba(245,158,11,0.80)',
          display: 'inline-block', flexShrink: 0,
        }} className="animate-pulse-soft" />
        <span style={{
          fontSize: 10, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.12em',
          color: '#f59e0b',
          fontFamily: 'JetBrains Mono, monospace',
        }}>
          Anomaly Console — {anomalies.length} Active
        </span>
      </div>

      {/* Anomaly cards */}
      {anomalies.map((anomaly) => {
        const sevLabel = severityLabel(anomaly.severity);
        const tok = getSeverityTokens(sevLabel);
        return (
          <div
            key={anomaly.anomaly_id}
            className="animate-fade-in"
            style={{
              padding: '12px 14px 12px 18px',
              background: tok.bg,
              border: `1px solid ${tok.border}`,
              borderRadius: 14,
              position: 'relative', overflow: 'hidden',
            }}
          >
            {/* Left severity bar */}
            <div style={{
              position: 'absolute', left: 0, top: 4, bottom: 4, width: 3,
              background: tok.accent, borderRadius: 99,
              boxShadow: `0 0 8px ${tok.accent}80`,
            }} />

            {/* Top row */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 6,
            }}>
              <span style={{
                display: 'flex', alignItems: 'center', gap: 7,
                fontSize: 13, color: tok.text, fontWeight: 600,
              }}>
                <span style={{ fontSize: 14 }}>{getTypeIcon(anomaly.type)}</span>
                <span style={{ textTransform: 'capitalize' }}>{anomaly.type}</span>
              </span>
              <SeverityBadge severity={sevLabel} />
            </div>

            {/* Description */}
            {anomaly.description && (
              <p style={{
                fontSize: 11, color: '#a3a3a3',
                lineHeight: 1.55, margin: '0 0 8px',
              }}>
                {anomaly.description}
              </p>
            )}

            {/* Footer meta */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              fontSize: 10, color: '#525252',
              fontFamily: 'JetBrains Mono, monospace',
            }}>
              <span>{(anomaly.edge_ids?.length || anomaly.affected_edges?.length || 0)} edge(s) affected</span>
              <span style={{ color: tok.accent }}>{anomaly.weight_multiplier}× weight</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}


// ─── Sub-Components ───────────────────────────────────────────────

function SeverityBadge({ severity }) {
  const styles = {
    low:      { bg: 'rgba(56,189,248,0.12)',  color: '#38bdf8', border: 'rgba(56,189,248,0.28)' },
    medium:   { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24', border: 'rgba(245,158,11,0.28)' },
    high:     { bg: 'rgba(249,115,22,0.12)',  color: '#fb923c', border: 'rgba(249,115,22,0.28)' },
    critical: { bg: 'rgba(239,68,68,0.12)',   color: '#f87171', border: 'rgba(239,68,68,0.28)' },
  };
  const s = styles[severity] || styles.low;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '2px 9px',
      background: s.bg,
      border: `1px solid ${s.border}`,
      borderRadius: 999,
      fontSize: 9, fontWeight: 800,
      letterSpacing: '0.10em', textTransform: 'uppercase',
      color: s.color,
      fontFamily: 'JetBrains Mono, monospace',
    }}>
      {severity}
    </span>
  );
}


// ─── Helpers ──────────────────────────────────────────────────────

function getSeverityTokens(severity) {
  return ({
    low:      { bg: 'rgba(56,189,248,0.05)', border: 'rgba(56,189,248,0.16)', text: '#7dd3fc', accent: '#38bdf8' },
    medium:   { bg: 'rgba(245,158,11,0.05)', border: 'rgba(245,158,11,0.16)', text: '#fcd34d', accent: '#f59e0b' },
    high:     { bg: 'rgba(249,115,22,0.06)', border: 'rgba(249,115,22,0.18)', text: '#fdba74', accent: '#f97316' },
    critical: { bg: 'rgba(239,68,68,0.07)',  border: 'rgba(239,68,68,0.20)', text: '#fca5a5', accent: '#ef4444' },
  })[severity] || { bg: 'rgba(56,189,248,0.05)', border: 'rgba(56,189,248,0.16)', text: '#7dd3fc', accent: '#38bdf8' };
}

function severityLabel(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 'low';
  if (n >= 8) return 'critical';
  if (n >= 5) return 'high';
  if (n >= 3) return 'medium';
  return 'low';
}

function getTypeIcon(type) {
  return ({ accident: '🚨', closure: '🚧', congestion: '🐌', weather: '🌧️', construction: '🏗️' })[type] || '⚠';
}

export default AnomalyAlert;
