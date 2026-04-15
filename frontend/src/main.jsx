/*
 * Frontend — Application Entry Point
 * =====================================
 * Mounts the React app to the DOM.
 * Imports global styles (TailwindCSS base + custom styles).
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import 'leaflet/dist/leaflet.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
