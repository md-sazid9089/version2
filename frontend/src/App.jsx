/*
 * Frontend — App Root Component
 * ================================
 * Main application shell with simple client-side routing.
 * Renders either the HomePage (landing) or MapPage (routing interface).
 *
 * Integration:
 *   - Wraps all pages with common layout (header/footer)
 *   - Manages page state (no React Router needed for hackathon scope)
 *   - Passes shared state (API connection status) to children
 */

import { useState, useEffect } from 'react';
import HomePage from './pages/HomePage';
import MapPage from './pages/MapPage';
import Footer from './components/Footer';
import { checkHealth } from './services/api';

function App() {
  const [currentPage, setCurrentPage] = useState('home'); // 'home' | 'map'
  const [apiStatus, setApiStatus] = useState(null);       // health check result

  // Check backend health on mount
  useEffect(() => {
    checkHealth()
      .then(setApiStatus)
      .catch(() => setApiStatus({ status: 'offline' }));
  }, []);

  /* ── Status indicator helpers ── */
  const statusDot =
    (apiStatus?.status === 'healthy' || apiStatus?.status === 'ok')  ? { bg: '#22c55e', shadow: 'rgba(34,197,94,0.6)'  } :
    apiStatus?.status === 'degraded' ? { bg: '#f59e0b', shadow: 'rgba(245,158,11,0.6)' } :
                                       { bg: '#ef4444', shadow: 'none' };
  const statusLabel =
    (apiStatus?.status === 'healthy' || apiStatus?.status === 'ok')  ? 'Engine Online' :
    apiStatus?.status === 'degraded' ? 'Degraded' :
                                       'Offline';

  const isMapPage = currentPage === 'map';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#0a0d14' }}>

      {/* ══════════════════════════════════════════════════
          NAVBAR — floating pill bar, z-index 100
          On the map page this floats above the full-screen map.
      ══════════════════════════════════════════════════ */}
      <header style={{
        position: 'fixed', top: 0, left: 0, right: 0,
        zIndex: 100,
        padding: '10px 20px',
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',           /* let clicks pass through padding area */
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: isMapPage
            ? 'rgba(22,22,24,0.88)'
            : 'rgba(17,21,32,0.90)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 999,
          padding: '7px 10px',
          boxShadow: '0 8px 40px rgba(0,0,0,0.55)',
          pointerEvents: 'all',          /* re-enable clicks on the pill */
          transition: 'background 0.3s ease',
        }}>

          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingRight: 10, borderRight: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: isMapPage
                ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                : 'linear-gradient(135deg, #0ea5e9, #14b8a6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 13, fontWeight: 700,
              boxShadow: isMapPage
                ? '0 0 12px rgba(34,197,94,0.40)'
                : '0 0 12px rgba(14,165,233,0.35)',
              transition: 'all 0.3s ease',
            }}>
              ⬡
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em', lineHeight: 1.1 }}>
                GoliTransit
                <span style={{
                  color: isMapPage ? '#22c55e' : '#38bdf8',
                  marginLeft: 3, fontSize: 11, fontWeight: 500,
                }}>AI</span>
              </div>
              <div style={{ fontSize: 8, color: '#525252', textTransform: 'uppercase', letterSpacing: '0.10em', fontFamily: 'JetBrains Mono, monospace' }}>
                Routing Engine v0.1
              </div>
            </div>
          </div>

          {/* Launch CTA — green */}
          <button
            onClick={() => setCurrentPage('map')}
            style={{
              padding: '7px 18px',
              borderRadius: 999, fontSize: 13, fontWeight: 700,
              border: 'none', cursor: 'pointer',
              background: '#22c55e',
              color: '#0a0a0a',
              boxShadow: '0 4px 16px rgba(34,197,94,0.35)',
              transition: 'transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = 'scale(1.04)';
              e.currentTarget.style.boxShadow = '0 6px 22px rgba(34,197,94,0.55)';
              e.currentTarget.style.filter = 'brightness(1.06)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(34,197,94,0.35)';
              e.currentTarget.style.filter = 'brightness(1)';
            }}
          >
            Launch Engine →
          </button>

          {/* Status capsule */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '5px 12px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 999,
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: statusDot.bg,
              boxShadow: statusDot.shadow !== 'none' ? `0 0 7px ${statusDot.shadow}` : 'none',
              display: 'inline-block',
              animation: apiStatus?.status !== 'offline' ? 'pulseSoft 2s ease-in-out infinite' : 'none',
            }} />
            <span style={{
              fontSize: 11, color: '#737373',
              fontFamily: 'JetBrains Mono, monospace',
              whiteSpace: 'nowrap',
            }}>
              {statusLabel}
            </span>
          </div>

        </div>
      </header>

      {/* ══════════════════════════════════════════════════
          PAGE CONTENT
          - On map page: MapPage uses position:fixed independently
          - On home page: normal flow content with no top padding (hero extends behind navbar)
      ══════════════════════════════════════════════════ */}
      <main style={{
        flex: 1, position: 'relative', display: 'flex', flexDirection: 'column',
        paddingTop: 0,
      }}>
        {currentPage === 'home' ? (
          <HomePage onNavigateToMap={() => setCurrentPage('map')} apiStatus={apiStatus} />
        ) : (
          <MapPage apiStatus={apiStatus} onGoBack={() => setCurrentPage('home')} />
        )}
      </main>

      {/* Footer — hidden on map page */}
      {!isMapPage && (
        <Footer />
      )}
    </div>
  );
}

export default App;
