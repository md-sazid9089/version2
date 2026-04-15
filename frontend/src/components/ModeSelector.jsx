/*
 * ModeSelector — Transport Mode Picker Component
 * ==================================================
 * HUD-style mode picker matching the design spec.
 * Grid of transport modes with glow effects on selection.
 * Sequence bar shows the current multi-modal route chain.
 */

const AVAILABLE_MODES = [
  { id: 'car',      label: 'Car',      icon: '\u{1F697}' },
  { id: 'bike',     label: 'Bike',     icon: '\u{1F6B2}' },
  { id: 'walk',     label: 'Walk',     icon: '\u{1F6B6}' },
  { id: 'transit',  label: 'Bus',      icon: '\u{1F68C}' },
  { id: 'rickshaw', label: 'Rickshaw', icon: '\u{1F6FA}' },
];

function ModeSelector({ selectedModes, onChange, routeMode = 'single', onRouteModeChange }) {
  const selectSingle = (modeId) => onChange([modeId]);
  const isMultimodal = routeMode === 'multimodal';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Section header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        paddingBottom: 12,
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        <div style={{
          width: 34, height: 34,
          borderRadius: 11,
          background: 'linear-gradient(135deg, rgba(139,92,246,0.20), rgba(139,92,246,0.06))',
          border: '1px solid rgba(139,92,246,0.25)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16,
        }}>
          {'\u{1F6A6}'}
        </div>
        <div>
          <div style={{
            fontSize: 15, fontWeight: 800, color: '#fff',
            letterSpacing: '-0.01em',
            fontFamily: 'Inter, system-ui, sans-serif',
          }}>
            Transport Mode
          </div>
          <div style={{
            fontSize: 9, color: '#525252',
            fontFamily: 'JetBrains Mono, monospace',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            marginTop: 1,
          }}>
            Select your mode
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={() => onRouteModeChange && onRouteModeChange('single')}
          style={{
            flex: 1,
            padding: '8px 10px',
            borderRadius: 10,
            border: routeMode === 'single'
              ? '1.5px solid rgba(34,197,94,0.5)'
              : '1.5px solid rgba(255,255,255,0.08)',
            background: routeMode === 'single'
              ? 'rgba(34,197,94,0.16)'
              : 'rgba(255,255,255,0.03)',
            color: routeMode === 'single' ? '#86efac' : '#a3a3a3',
            fontWeight: 700,
            fontSize: 11,
            fontFamily: 'Inter, system-ui, sans-serif',
            cursor: 'pointer',
          }}
        >
          Single Mode
        </button>
        <button
          onClick={() => onRouteModeChange && onRouteModeChange('multimodal')}
          style={{
            flex: 1,
            padding: '8px 10px',
            borderRadius: 10,
            border: routeMode === 'multimodal'
              ? '1.5px solid rgba(59,130,246,0.5)'
              : '1.5px solid rgba(255,255,255,0.08)',
            background: routeMode === 'multimodal'
              ? 'rgba(59,130,246,0.16)'
              : 'rgba(255,255,255,0.03)',
            color: routeMode === 'multimodal' ? '#93c5fd' : '#a3a3a3',
            fontWeight: 700,
            fontSize: 11,
            fontFamily: 'Inter, system-ui, sans-serif',
            cursor: 'pointer',
          }}
        >
          Multimodal
        </button>
      </div>

      {/* Mode grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 7 }}>
        {AVAILABLE_MODES.map((mode) => {
          const isActive = selectedModes.includes(mode.id);
          const isPrimary = selectedModes.length === 1 && selectedModes[0] === mode.id;

          return (
            <button
              key={mode.id}
              id={`mode-btn-${mode.id}`}
              onClick={() => selectSingle(mode.id)}
              disabled={isMultimodal}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                padding: '12px 6px',
                borderRadius: 16,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'Inter, system-ui, sans-serif',
                letterSpacing: '0.01em',
                cursor: isMultimodal ? 'not-allowed' : 'pointer',
                border: isPrimary
                  ? '1.5px solid rgba(139,92,246,0.55)'
                  : isActive
                    ? '1.5px solid rgba(139,92,246,0.30)'
                    : '1.5px solid rgba(255,255,255,0.06)',
                transition: 'all 0.2s cubic-bezier(0.4,0,0.2,1)',
                background: isPrimary
                  ? 'linear-gradient(145deg, rgba(124,58,237,0.90), rgba(139,92,246,0.80))'
                  : isActive
                    ? 'rgba(139,92,246,0.12)'
                    : 'rgba(255,255,255,0.03)',
                color: isMultimodal ? '#4b5563' : (isPrimary ? '#fff' : isActive ? '#c4b5fd' : '#737373'),
                boxShadow: isPrimary
                  ? '0 8px 24px rgba(139,92,246,0.40), inset 0 1px 0 rgba(255,255,255,0.10)'
                  : 'none',
                transform: isPrimary ? 'translateY(-1px)' : 'none',
                opacity: isMultimodal ? 0.55 : 1,
              }}
            >
              <span style={{ fontSize: 22, lineHeight: 1 }}>{mode.icon}</span>
              <span style={{ lineHeight: 1 }}>{mode.label}</span>
            </button>
          );
        })}
      </div>

      {/* Single-mode summary */}
      <div style={{
        background: 'rgba(0,0,0,0.30)',
        border: '1px solid rgba(255,255,255,0.05)',
        borderRadius: 14,
        padding: '9px 12px',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span style={{
            fontSize: 9, fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            color: '#404040',
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            Selected Mode
          </span>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            color: '#a78bfa',
            fontFamily: 'Inter, system-ui, sans-serif',
            textTransform: 'capitalize',
          }}>
            {isMultimodal ? 'multimodal auto' : ((selectedModes && selectedModes[0]) || 'car')}
          </span>
        </div>
      </div>
    </div>
  );
}

export default ModeSelector;
