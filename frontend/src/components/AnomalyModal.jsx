import { useState, useEffect } from 'react';

const ANOMALY_TYPES = [
  { id: 'traffic_congestion', label: 'Traffic Congestion' },
  { id: 'road_block', label: 'Road Block / Closure' },
  { id: 'waterlogging', label: 'Waterlogging / Flood' },
  { id: 'vip_movement', label: 'VIP Movement' },
  { id: 'public_transport_delay', label: 'Public Transport Delay' },
  { id: 'partial_lane_block', label: 'Partial Lane Block' },
  { id: 'pedestrian_only_zone', label: 'Pedestrian-Only Zone' },
];

const ANOMALY_PRESETS = {
  traffic_congestion: {
    severity: 3,
    vehicleTypes: ['car', 'bus', 'bike'],
    summary: 'Slows motor traffic and bikes on the selected road or area.',
  },
  road_block: {
    severity: 5,
    vehicleTypes: ['car', 'bus', 'bike', 'rickshaw', 'walk'],
    summary: 'Blocks the affected corridor for all modes.',
  },
  waterlogging: {
    severity: 4,
    vehicleTypes: ['car', 'bike', 'rickshaw', 'walk'],
    summary: 'Makes surface travel slower and may push reroutes away from the area.',
  },
  vip_movement: {
    severity: 5,
    vehicleTypes: ['car', 'bus'],
    summary: 'Disables car and bus routing on main roads in the affected area.',
  },
  public_transport_delay: {
    severity: 3,
    vehicleTypes: ['bus'],
    summary: 'Slows transit legs without changing private modes.',
  },
  partial_lane_block: {
    severity: 3,
    vehicleTypes: ['car', 'bus', 'bike', 'rickshaw'],
    summary: 'Adds moderate delay across all road vehicles.',
  },
  pedestrian_only_zone: {
    severity: 4,
    vehicleTypes: ['car', 'bike'],
    summary: 'Removes motorized access and prioritizes walking routes.',
  },
};

function getPreset(type) {
  return ANOMALY_PRESETS[type] || ANOMALY_PRESETS.traffic_congestion;
}

function AnomalyModal({ isOpen, onClose, onSubmit, target }) {
  const [anomalyType, setAnomalyType] = useState('traffic_congestion');
  const [severity, setSeverity] = useState(3);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');

  const preset = getPreset(anomalyType);

  useEffect(() => {
    if (isOpen) {
      const defaultType = 'traffic_congestion';
      const defaultPreset = getPreset(defaultType);
      setAnomalyType(defaultType);
      setSeverity(defaultPreset.severity);
      setStartTime('');
      setEndTime('');
    }
  }, [isOpen]);

  useEffect(() => {
    const nextPreset = getPreset(anomalyType);
    setSeverity(nextPreset.severity);
  }, [anomalyType]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      anomalyType,
      severity: preset.severity,
      vehicleTypes: preset.vehicleTypes,
      startTime: startTime || null,
      endTime: endTime || null,
    });
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        className="animate-slide-up"
        style={{
          background: 'rgba(18,18,22,0.95)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 20,
          padding: '24px',
          width: 380,
          maxWidth: '92%',
          boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, color: '#fff', fontSize: 18, fontFamily: 'Inter, system-ui, sans-serif' }}>
            Apply Anomaly
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#a3a3a3',
              fontSize: 20,
              cursor: 'pointer',
            }}
          >
            &times;
          </button>
        </div>

        {target && (
          <div
            style={{
              padding: '10px 14px',
              background: 'rgba(255,255,255,0.03)',
              borderRadius: 10,
              fontSize: 12,
              color: '#a3a3a3',
              fontFamily: 'JetBrains Mono, monospace',
            }}
          >
            {target.type === 'edge' ? (
              <>
                Target Edge:{' '}
                <span style={{ color: '#f59e0b', fontWeight: 600 }}>{target.edgeId || 'N/A'}</span>
              </>
            ) : (
              <>
                Target BBox:{' '}
                <span style={{ color: '#f59e0b', fontWeight: 600 }}>
                  {target.bbox ? target.bbox.map((v) => Number(v).toFixed(5)).join(', ') : 'N/A'}
                </span>
              </>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: '#a3a3a3',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Anomaly Type
            </label>
            <select
              value={anomalyType}
              onChange={(e) => setAnomalyType(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 10,
                border: '1px solid rgba(255,255,255,0.12)',
                background: 'rgba(0,0,0,0.25)',
                color: '#f4f4f5',
                fontSize: 13,
              }}
            >
              {ANOMALY_TYPES.map((t) => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
            <div style={{ color: '#fbbf24', fontSize: 11, lineHeight: 1.5 }}>
              {preset.summary}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: '#a3a3a3',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Severity Multiplier
            </label>
            <div style={{
              padding: '10px 12px',
              borderRadius: 10,
              border: '1px solid rgba(245,158,11,0.20)',
              background: 'rgba(0,0,0,0.22)',
              color: '#fbbf24',
              fontSize: 13,
              fontWeight: 700,
            }}>
              Auto-set to {severity} based on the selected anomaly type
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: '#a3a3a3',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Affected Modes
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {preset.vehicleTypes.map((vehicleId) => (
                <span
                  key={vehicleId}
                  style={{
                    padding: '6px 10px',
                    borderRadius: 999,
                    border: '1px solid rgba(245,158,11,0.28)',
                    background: 'rgba(245,158,11,0.10)',
                    color: '#fbbf24',
                    fontSize: 12,
                    fontWeight: 700,
                    textTransform: 'capitalize',
                  }}
                >
                  {vehicleId === 'bus' ? 'Bus' : vehicleId}
                </span>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 10, color: '#a3a3a3' }}>Start Time (optional)</label>
              <input
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.12)',
                  background: 'rgba(0,0,0,0.25)',
                  color: '#f4f4f5',
                  fontSize: 12,
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 10, color: '#a3a3a3' }}>End Time (optional)</label>
              <input
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.12)',
                  background: 'rgba(0,0,0,0.25)',
                  color: '#f4f4f5',
                  fontSize: 12,
                }}
              />
            </div>
          </div>

          <button
            type="submit"
            style={{
              marginTop: 10,
              padding: '14px',
              borderRadius: 12,
              border: 'none',
              background: 'linear-gradient(135deg, #f59e0b, #d97706)',
              color: '#fff',
              fontSize: 14,
              fontWeight: 800,
              cursor: 'pointer',
              boxShadow: '0 8px 24px rgba(245,158,11,0.3)',
            }}
          >
            Apply Anomaly
          </button>
        </form>
      </div>
    </div>
  );
}

export default AnomalyModal;
