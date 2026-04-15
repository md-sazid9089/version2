/*
 * Footer Component — Modern, Clean Design
 * ========================================
 * Displays company info, links, and copyright
 * No icons required, text-based layout
 */

export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="app-footer">
      {/* Main footer content */}
      <div className="footer-container">
        
        {/* Left: Brand & About */}
        <div className="footer-section footer-brand">
          <div className="footer-logo">
            <span className="footer-logo-text">GoliTransit AI</span>
            <span className="footer-tagline">Multi-Modal Routing</span>
          </div>
          <p className="footer-description">
            Hyper-local routing engine powered by AI. Optimized for pedestrians, cyclists, and drivers.
          </p>
        </div>

        {/* Center: Links */}
        <div className="footer-links-group">
          <div className="footer-section footer-links">
            <h4 className="footer-section-title">Product</h4>
            <ul>
              <li><a href="#features">Features</a></li>
              <li><a href="#pricing">Pricing</a></li>
              <li><a href="#api">API Docs</a></li>
              <li><a href="#status">Status</a></li>
            </ul>
          </div>

          <div className="footer-section footer-links">
            <h4 className="footer-section-title">Company</h4>
            <ul>
              <li><a href="#about">About Us</a></li>
              <li><a href="#careers">Careers</a></li>
              <li><a href="#blog">Blog</a></li>
              <li><a href="#contact">Contact</a></li>
            </ul>
          </div>

          <div className="footer-section footer-links">
            <h4 className="footer-section-title">Resources</h4>
            <ul>
              <li><a href="#docs">Documentation</a></li>
              <li><a href="#guide">Quick Start</a></li>
              <li><a href="#faq">FAQ</a></li>
              <li><a href="#support">Support</a></li>
            </ul>
          </div>

          <div className="footer-section footer-links">
            <h4 className="footer-section-title">Legal</h4>
            <ul>
              <li><a href="#privacy">Privacy Policy</a></li>
              <li><a href="#terms">Terms of Service</a></li>
              <li><a href="#cookies">Cookies</a></li>
              <li><a href="#compliance">Compliance</a></li>
            </ul>
          </div>
        </div>
      </div>

      {/* Bottom: Divider & Copyright */}
      <div className="footer-divider" />
      
      <div className="footer-bottom">
        <div className="footer-copyright">
          <p>&copy; {currentYear} GoliTransit AI. All rights reserved.</p>
          <span className="footer-version">v0.1.0-hackathon</span>
        </div>
        <div className="footer-status-line">
          <span className="status-indicator">●</span>
          <span>All systems operational</span>
        </div>
      </div>
    </footer>
  );
}
