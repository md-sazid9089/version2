/*
 * RoutePanel — Route Input & Results HUD Card
 * =============================================
 * Matches the design spec with:
 *   - Mode icon + name + LEG badge header
 *   - Metric row: distance | duration | cost
 *   - Vehicle recommendations section
 *   - Route step breakdown with road names
 *   - Dual-route comparison cards for multimodal mode
 */


const MODE_COLORS = {
  car:      '#3b82f6',
  bike:     '#34d399',
  walk:     '#9ca3af',
  transit:  '#ef4444',
  bus:      '#ef4444',
  rickshaw: '#f97316',
};

function RoutePanel({ 
  origin, 
  destination, 
  routeResult, 
  dualRoute, 
  routeMode, 
  isLoading, 
  error, 
  onCompute, 
  onComputeMultimodal, 
  onRouteModeChange,
  onClear 
}) {
  const hasPoints = origin && destination;
  const isMultimodalMode = routeMode === 'multimodal';

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* Section header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        paddingBottom: 12,
        borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        <div style={{
          width: 28, height: 28,
          borderRadius: 9,
          background: 'linear-gradient(135deg, rgba(34,197,94,0.20), rgba(34,197,94,0.06))',
          border: '1px solid rgba(34,197,94,0.25)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13,
        }}>
          {'\u{1F5FA}'}
        </div>
        <div>
          <div style={{
            fontSize: 14, fontWeight: 800, color: '#fff',
            letterSpacing: '-0.01em',
            fontFamily: 'Inter, system-ui, sans-serif',
          }}>
            Route Planner
          </div>
          <div style={{
            fontSize: 9, color: '#525252',
            fontFamily: 'JetBrains Mono, monospace',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}>
            {!origin ? 'Set origin on map' : !destination ? 'Set destination on map' : 'Ready to compute'}
          </div>
        </div>
      </div>

      {/* Waypoints */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <WaypointDisplay label="Origin" latlng={origin} accentColor="#22c55e" emptyText="Tap map to set origin" />
        <WaypointDisplay label="Destination" latlng={destination} accentColor="#8b5cf6" emptyText="Tap map to set destination" />
      </div>

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          id="btn-compute-route"
          onClick={onCompute}
          disabled={!hasPoints || isLoading || isMultimodalMode}
          style={{
            flex: 1,
            padding: '12px 0',
            borderRadius: 14,
            border: 'none',
            cursor: (!hasPoints || isLoading || isMultimodalMode) ? 'not-allowed' : 'pointer',
            fontWeight: 800,
            fontSize: 13,
            fontFamily: 'Inter, system-ui, sans-serif',
            letterSpacing: '-0.01em',
            background: (!hasPoints || isLoading || isMultimodalMode)
              ? 'rgba(255,255,255,0.04)'
              : 'linear-gradient(135deg, #16a34a, #22c55e)',
            color: (!hasPoints || isLoading || isMultimodalMode) ? '#404040' : '#0a0a0a',
            boxShadow: (!hasPoints || isLoading || isMultimodalMode)
              ? 'none'
              : '0 8px 24px rgba(34,197,94,0.35), inset 0 1px 0 rgba(255,255,255,0.15)',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={e => {
            if (hasPoints && !isLoading && !isMultimodalMode) {
              e.currentTarget.style.transform = 'translateY(-1px)';
              e.currentTarget.style.boxShadow = '0 12px 32px rgba(34,197,94,0.50), inset 0 1px 0 rgba(255,255,255,0.15)';
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform = 'none';
            e.currentTarget.style.boxShadow = (!hasPoints || isLoading || isMultimodalMode) ? 'none'
              : '0 8px 24px rgba(34,197,94,0.35), inset 0 1px 0 rgba(255,255,255,0.15)';
          }}
        >
          {isLoading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <span style={{
                width: 14, height: 14,
                border: '2.5px solid rgba(10,10,10,0.25)',
                borderTopColor: '#0a0a0a',
                borderRadius: '50%',
                display: 'inline-block',
                animation: 'spin 0.7s linear infinite',
              }} />
              Computing...
            </span>
          ) : 'Compute Route'}
        </button>

        <button
          id="btn-compute-multimodal"
          onClick={onComputeMultimodal}
          disabled={!hasPoints || isLoading || !isMultimodalMode}
          style={{
            padding: '12px 10px',
            borderRadius: 14,
            border: '1.5px solid rgba(59,130,246,0.35)',
            background: (!hasPoints || isLoading || !isMultimodalMode)
              ? 'rgba(255,255,255,0.03)'
              : 'rgba(59,130,246,0.12)',
            color: (!hasPoints || isLoading || !isMultimodalMode) ? '#404040' : '#93c5fd',
            fontWeight: 700,
            fontSize: 11,
            fontFamily: 'Inter, system-ui, sans-serif',
            cursor: (!hasPoints || isLoading || !isMultimodalMode) ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          Multimodal
        </button>

        <button
          id="btn-clear-route"
          onClick={onClear}
          style={{
            padding: '12px 16px',
            borderRadius: 14,
            border: '1.5px solid rgba(255,255,255,0.08)',
            background: 'transparent',
            color: '#525252',
            fontWeight: 700,
            fontSize: 12,
            fontFamily: 'Inter, system-ui, sans-serif',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
            e.currentTarget.style.color = '#fff';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = '#525252';
          }}
        >
          Clear
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="animate-slide-up" style={{
          padding: '10px 14px',
          background: 'rgba(239,68,68,0.07)',
          border: '1px solid rgba(239,68,68,0.20)',
          borderRadius: 12,
          fontSize: 11,
          fontWeight: 600,
          color: '#f87171',
          lineHeight: 1.5,
          fontFamily: 'Inter, system-ui, sans-serif',
        }}>
          {'\u26A0'} {error}
        </div>
      )}

      {/* Route result */}
      {routeResult && (
        <div className="animate-slide-up" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {!isMultimodalMode && routeResult.legs.map((leg, idx) => (
            <LegCard key={idx} leg={leg} index={idx} totalLegs={routeResult.legs.length} />
          ))}

          {/* Mode switches */}
          {!isMultimodalMode && routeResult.mode_switches?.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <SectionLabel text="Mode Transfers" />
              {routeResult.mode_switches.map((sw, idx) => (
                <div key={idx} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.25)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  borderRadius: 10,
                }}>
                  <span style={{ fontSize: 15 }}>{getModeEmoji(sw.from_mode)}</span>
                  <span style={{ color: '#333', fontFamily: 'JetBrains Mono, monospace', fontWeight: 700 }}>{'\u2192'}</span>
                  <span style={{ fontSize: 15 }}>{getModeEmoji(sw.to_mode)}</span>
                  <span style={{
                    marginLeft: 'auto',
                    color: '#f59e0b',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: 11, fontWeight: 700,
                  }}>
                    +{sw.penalty_time_s}s
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Anomalies avoided */}
          {!isMultimodalMode && routeResult.anomalies_avoided > 0 && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(245,158,11,0.06)',
              border: '1px solid rgba(245,158,11,0.18)',
              borderRadius: 10,
              fontSize: 12,
              fontWeight: 600,
              color: '#f59e0b',
              display: 'flex', alignItems: 'center', gap: 8,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}>
              {'\u26A0'} Avoided {routeResult.anomalies_avoided} anomaly-affected edge(s)
            </div>
          )}

          {/* Traffic jam chance */}
          {routeResult.traffic_status === 'loading' && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(59,130,246,0.08)',
              border: '1px solid rgba(59,130,246,0.25)',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: '#93c5fd',
              fontSize: 12,
              fontWeight: 700,
            }}>
              <span style={{
                width: 12,
                height: 12,
                border: '2px solid rgba(147,197,253,0.35)',
                borderTopColor: '#93c5fd',
                borderRadius: '50%',
                display: 'inline-block',
                animation: 'spin 0.7s linear infinite',
              }} />
              Loading traffic...
            </div>
          )}

          {routeResult.traffic_status === 'failed' && (
            <div style={{
              padding: '10px 14px',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.25)',
              borderRadius: 10,
              color: '#f87171',
              fontSize: 12,
              fontWeight: 700,
            }}>
              Traffic prediction failed. Route is still valid.
            </div>
          )}

          {routeResult.traffic_status === 'ready' && routeResult.traffic_jam_prediction && (
            <TrafficJamCard data={routeResult.traffic_jam_prediction} />
          )}

          {/* Real multimodal recommendation output */}
          {false && isMultimodalMode && Array.isArray(routeResult.multimodal_suggestions) && routeResult.multimodal_suggestions.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <SectionLabel text="Multimodal Suggestions" icon={'\u2728'} />
              {routeResult.multimodal_suggestions.map((s, idx) => (
                <div key={`${s.strategy}-${idx}`} style={{
                  background: 'rgba(0,0,0,0.25)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  borderRadius: 12,
                  padding: '10px 12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{
                      fontSize: 11,
                      fontWeight: 800,
                      color: '#fff',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      fontFamily: 'JetBrains Mono, monospace',
                    }}>
                      {s.strategy === 'shortest_distance' ? 'Shortest Distance' : 'Fastest Time'}
                    </div>
                    <div style={{
                      fontSize: 10,
                      color: '#a3a3a3',
                      fontFamily: 'JetBrains Mono, monospace',
                    }}>
                      {formatDistance(s.total_distance_m)} | {formatDuration(s.total_duration_s)}
                    </div>
                  </div>

                  {(s.segments || []).slice(0, 8).map((seg) => (
                    <div key={`${s.strategy}-${seg.segment_index}`} style={{
                      border: '1px solid rgba(255,255,255,0.04)',
                      borderRadius: 8,
                      padding: '7px 8px',
                      background: 'rgba(255,255,255,0.015)',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                        <span style={{ color: '#737373', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}>
                          Segment {seg.segment_index + 1} - {seg.road_type}
                        </span>
                        <span style={{ color: '#a3a3a3', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}>
                          {formatDistance(seg.distance_m)}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{
                          color: MODE_COLORS[seg.recommended_vehicle] || '#22c55e',
                          fontSize: 11,
                          fontWeight: 700,
                          textTransform: 'capitalize',
                        }}>
                          Fastest: {getModeLabel(seg.recommended_vehicle)}
                        </span>
                        <span style={{ color: '#525252', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}>
                          {(seg.vehicle_options || [])
                            .sort((a, b) => vehicleOrder(a.vehicle) - vehicleOrder(b.vehicle))
                            .map((v) => (
                              v.allowed
                                ? `${getModeLabel(v.vehicle)}:${formatDuration(v.travel_time_s)}`
                                : `${getModeLabel(v.vehicle)}:N/A`
                            ))
                            .join(' | ')}
                        </span>
                      </div>
                    </div>
                  ))}

                  {(s.segments || []).length > 8 && (
                    <div style={{ color: '#525252', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}>
                      +{s.segments.length - 8} more segments
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}


// --- Sub-Components ---

function WaypointDisplay({ label, latlng, accentColor, emptyText }) {
  const coordText = latlng ? `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}` : null;
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      padding: '8px 12px',
      background: latlng ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.15)',
      border: latlng ? `1px solid ${accentColor}22` : '1px solid rgba(255,255,255,0.04)',
      borderRadius: 12,
      transition: 'all 0.2s ease',
    }}>
      <div style={{
        width: 9, height: 9,
        borderRadius: '50%',
        flexShrink: 0,
        background: latlng ? accentColor : '#2e2e30',
        boxShadow: latlng ? `0 0 10px ${accentColor}60` : 'none',
        transition: 'all 0.2s ease',
      }} />
      <span style={{
        fontSize: 9, fontWeight: 800,
        textTransform: 'uppercase',
        letterSpacing: '0.10em',
        color: latlng ? accentColor : '#333',
        fontFamily: 'JetBrains Mono, monospace',
        width: 60, flexShrink: 0,
      }}>
        {label}
      </span>
      {latlng ? (
        <span style={{
          color: '#a3a3a3',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 10, fontWeight: 500,
          overflow: 'hidden', whiteSpace: 'nowrap',
          textOverflow: 'ellipsis', flex: 1, minWidth: 0,
        }}>
          {coordText}
        </span>
      ) : (
        <span style={{
          color: '#333', fontSize: 12, fontWeight: 500,
          fontStyle: 'italic', fontFamily: 'Inter, system-ui, sans-serif',
        }}>
          {emptyText}
        </span>
      )}
    </div>
  );
}

function formatHourOfDay(hour) {
  const h = Number.isFinite(hour) ? Number(hour) : 0;
  const normalized = ((h % 24) + 24) % 24;
  const hour12 = normalized % 12 === 0 ? 12 : normalized % 12;
  const ampm = normalized < 12 ? 'AM' : 'PM';
  return `${hour12}:00 ${ampm}`;
}

function LegCard({ leg, index, totalLegs }) {
  const accent = MODE_COLORS[leg.mode] || '#22c55e';
  return (
    <div style={{
      background: 'rgba(0,0,0,0.25)',
      border: '1px solid rgba(255,255,255,0.05)',
      borderRadius: 16,
      padding: '14px 14px 14px 18px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Left accent stripe */}
      <div style={{
        position: 'absolute', left: 0, top: 6, bottom: 6, width: 3,
        background: accent, borderRadius: 99,
        boxShadow: `0 0 10px ${accent}60`,
      }} />

      {/* Header: mode + leg badge */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 8,
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 18 }}>{getModeEmoji(leg.mode)}</span>
          <span style={{
            textTransform: 'capitalize',
            color: accent,
            fontSize: 15,
            fontWeight: 800,
            fontFamily: 'Inter, system-ui, sans-serif',
            letterSpacing: '-0.01em',
          }}>
            {getModeLabel(leg.mode)}
          </span>
        </span>
        <span style={{
          fontSize: 9, color: '#525252',
          fontFamily: 'JetBrains Mono, monospace',
          fontWeight: 700,
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 6,
          padding: '3px 10px',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
        }}>
          Leg {index + 1}
        </span>
      </div>

      {/* Metric row */}
      <div style={{
        display: 'flex',
        gap: 14,
        fontSize: 13,
        fontWeight: 600,
        fontFamily: 'JetBrains Mono, monospace',
        marginBottom: 12,
        paddingBottom: 10,
        borderBottom: '1px solid rgba(255,255,255,0.04)',
      }}>
        <span style={{ color: '#a3a3a3' }}>{formatDistance(leg.distance_m)}</span>
        <span style={{ color: '#a3a3a3' }}>{formatDuration(leg.duration_s)}</span>
        <span style={{ color: '#f59e0b', fontWeight: 700 }}>${leg.cost.toFixed(2)}</span>
      </div>

      {/* Vehicle recommendations */}
      <SectionLabel text="Vehicle Recommendations" icon={'\u2728'} />

      <div style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.04)',
        borderRadius: 12,
        padding: '10px 12px',
        marginTop: 6,
      }}>
        {/* Shortest distance row */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 13 }}>{'\u26A1'}</span>
            <span style={{
              fontSize: 12, fontWeight: 800, color: '#fff',
              fontFamily: 'Inter, system-ui, sans-serif',
            }}>
              Shortest Distance
            </span>
          </div>
          <div style={{
            display: 'flex', gap: 8,
            fontSize: 10, color: '#737373',
            fontFamily: 'JetBrains Mono, monospace', fontWeight: 600,
          }}>
            <span>{formatDistance(leg.distance_m)}</span>
            <span>{formatDuration(leg.duration_s)}</span>
          </div>
        </div>

        {/* Route instructions */}
        {leg.instructions && leg.instructions.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {leg.instructions.map((instr, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '5px 8px',
                background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                borderRadius: 6,
                fontSize: 10,
                fontFamily: 'JetBrains Mono, monospace',
                color: '#737373',
              }}>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {instr}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Fastest label */}
        <div style={{
          marginTop: 8,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '4px 10px',
            background: `${accent}18`,
            border: `1px solid ${accent}35`,
            borderRadius: 999,
            fontSize: 9, fontWeight: 800,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: accent,
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            Fastest: {getModeLabel(leg.mode)}
          </span>
          <span style={{
            fontSize: 10, color: '#525252',
            fontFamily: 'JetBrains Mono, monospace',
          }}>
            {formatDuration(leg.duration_s)}
          </span>
          <span style={{
            marginLeft: 'auto',
            color: '#22c55e',
            fontSize: 13,
          }}>
            {'\u2714'}
          </span>
        </div>
      </div>
    </div>
  );
}

function SectionLabel({ text, icon }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 800,
      textTransform: 'uppercase',
      letterSpacing: '0.14em',
      color: '#404040',
      fontFamily: 'JetBrains Mono, monospace',
      display: 'flex', alignItems: 'center', gap: 5,
      paddingLeft: 2,
    }}>
      {icon && <span style={{ fontSize: 10 }}>{icon}</span>}
      {text}
    </div>
  );
}

function MetricCell({ value, label, accent, borderRight }) {
  return (
    <div style={{
      padding: '8px 8px 9px',
      textAlign: 'center',
      borderRight: borderRight ? '1px solid rgba(255,255,255,0.04)' : 'none',
    }}>
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 16, fontWeight: 800,
        color: accent || '#fff',
        marginBottom: 2,
        letterSpacing: '-0.02em',
      }}>
        {value}
      </div>
      <div style={{
        fontSize: 9, color: '#525252',
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        fontWeight: 700,
        fontFamily: 'JetBrains Mono, monospace',
      }}>
        {label}
      </div>
    </div>
  );
}


// --- Traffic Jam Card ---

function getJamTheme(pct) {
  if (pct >= 70) return {
    bg:     'rgba(239,68,68,0.10)',
    border: 'rgba(239,68,68,0.30)',
    bar:    'linear-gradient(90deg,#ef4444,#dc2626)',
    text:   '#f87171',
    label:  'HIGH RISK',
    icon:   '🔴',
    glow:   'rgba(239,68,68,0.25)',
  };
  if (pct >= 40) return {
    bg:     'rgba(245,158,11,0.10)',
    border: 'rgba(245,158,11,0.30)',
    bar:    'linear-gradient(90deg,#f59e0b,#d97706)',
    text:   '#fbbf24',
    label:  'MODERATE',
    icon:   '🟡',
    glow:   'rgba(245,158,11,0.20)',
  };
  return {
    bg:     'rgba(34,197,94,0.08)',
    border: 'rgba(34,197,94,0.25)',
    bar:    'linear-gradient(90deg,#22c55e,#16a34a)',
    text:   '#4ade80',
    label:  'LOW RISK',
    icon:   '🟢',
    glow:   'rgba(34,197,94,0.15)',
  };
}

function TrafficJamCard({ data }) {
  const pct   = Number(data?.route_jam_chance_pct ?? 0);
  const heavy = Number(data?.heavy_edges ?? 0);
  const mod   = Number(data?.moderate_edges ?? 0);
  const low   = Number(data?.low_edges ?? 0);
  const total = Number(data?.edges_analyzed ?? 0);
  const hour  = data?.hour_of_day;
  const theme = getJamTheme(pct);

  return (
    <div className="traffic-jam-card animate-slide-up" style={{
      padding: '12px 14px',
      background: theme.bg,
      border: `1px solid ${theme.border}`,
      borderRadius: 14,
      display: 'flex',
      flexDirection: 'column',
      gap: 9,
      boxShadow: `0 4px 20px ${theme.glow}`,
    }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 16 }}>{theme.icon}</span>
          <div>
            <div style={{
              fontSize: 11, fontWeight: 800, color: '#e5e7eb',
              fontFamily: 'Inter, system-ui, sans-serif',
              letterSpacing: '-0.01em',
            }}>
              Traffic Jam Risk
            </div>
            <div style={{
              fontSize: 9, color: theme.text,
              fontFamily: 'JetBrains Mono, monospace',
              fontWeight: 700, letterSpacing: '0.10em',
            }}>
              {theme.label}
            </div>
          </div>
        </div>
        <span style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 28, fontWeight: 800,
          color: theme.text,
          lineHeight: 1,
          letterSpacing: '-0.03em',
        }}>
          {pct}<span style={{ fontSize: 14, opacity: 0.7 }}>%</span>
        </span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: 6, background: 'rgba(255,255,255,0.07)',
        borderRadius: 99, overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${Math.min(pct, 100)}%`,
          background: theme.bar,
          borderRadius: 99,
          transition: 'width 0.8s cubic-bezier(0.34,1.56,0.64,1)',
          boxShadow: `0 0 8px ${theme.glow}`,
        }} />
      </div>

      {/* Edge breakdown pills */}
      <div style={{ display: 'flex', gap: 6 }}>
        <EdgePill label="Heavy"    count={heavy} color="#ef4444" />
        <EdgePill label="Moderate" count={mod}   color="#f59e0b" />
        <EdgePill label="Clear"    count={low}   color="#22c55e" />
      </div>

      {/* Footer */}
      <div style={{
        fontSize: 9, color: '#525252',
        fontFamily: 'JetBrains Mono, monospace',
        display: 'flex', gap: 10,
      }}>
        {hour !== undefined && <span>⏰ {formatHourOfDay(hour)}</span>}
        <span>📊 {total} segments</span>
      </div>
    </div>
  );
}

function EdgePill({ label, count, color }) {
  return (
    <div style={{
      flex: 1,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '5px 4px',
      background: `${color}14`,
      border: `1px solid ${color}30`,
      borderRadius: 8,
      gap: 2,
    }}>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 14, fontWeight: 800, color,
        lineHeight: 1,
      }}>{count}</span>
      <span style={{
        fontSize: 8, color: '#737373',
        fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.08em',
        fontFamily: 'JetBrains Mono, monospace',
      }}>{label}</span>
    </div>
  );
}


// --- Helpers ---

function getModeEmoji(mode) {
  return ({
    car: '\u{1F697}',
    bike: '\u{1F6B2}',
    walk: '\u{1F6B6}',
    transit: '\u{1F68C}',
    bus: '\u{1F68C}',
    rickshaw: '\u{1F6FA}',
  })[mode] || '\u{1F4CD}';
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

function vehicleOrder(mode) {
  return ({
    transit: 1,
    bus: 1,
    car: 2,
    bike: 3,
    rickshaw: 4,
    walk: 5,
  })[mode] || 99;
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

export default RoutePanel;
