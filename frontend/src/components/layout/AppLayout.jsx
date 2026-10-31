import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const navigation = [
  ['Overview', '⌂'],
  ['Customers', '♙'],
  ['Products', '▦'],
  ['Plans', '◈'],
  ['Quotations', '▤'],
  ['Subscriptions', '↻'],
  ['Invoices', '▧'],
  ['Payments', '◉'],
  ['Discounts', '%'],
  ['Reports', '◫'],
]

function NavIcon({ glyph }) {
  return <span className="nav-icon" aria-hidden="true">{glyph}</span>
}

export default function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="app-shell">
      <button className="mobile-menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">☰</button>
      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">B</div>
          <div><strong>Brightloop</strong><span>Subscription OS</span></div>
          <button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">×</button>
        </div>
        <div className="workspace-switcher">
          <div className="workspace-avatar">AC</div>
          <div><strong>Acme Corporation</strong><span>Business workspace</span></div>
          <span className="chevron">⌄</span>
        </div>
        <p className="nav-label">Workspace</p>
        <nav className="sidebar-nav">
          {navigation.map(([label, glyph]) => (
            <NavLink
              key={label}
              to={label === 'Overview' ? '/' : `/${label.toLowerCase()}`}
              end={label === 'Overview'}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <NavIcon glyph={glyph} /> <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <NavLink to="/settings" className="nav-link"><NavIcon glyph="⚙" /><span>Settings</span></NavLink>
          <div className="help-card"><span className="help-icon">?</span><div><strong>Need a hand?</strong><span>Visit our help center</span></div><span>↗</span></div>
          <div className="profile-row"><div className="profile-avatar">JD</div><div><strong>Jordan Davis</strong><span>Administrator</span></div><span className="profile-more">•••</span></div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><b>/</b><strong>Overview</strong></div>
          <div className="topbar-actions">
            <label className="global-search"><span>⌕</span><input aria-label="Search" placeholder="Search anything..." /><kbd>⌘ K</kbd></label>
            <button className="icon-button" aria-label="Notifications">♢<i /></button>
            <button className="icon-button" aria-label="Help">?</button>
            <div className="top-profile"><div className="profile-avatar">JD</div><span className="chevron">⌄</span></div>
          </div>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  )
}
