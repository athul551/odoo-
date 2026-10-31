import { useState } from 'react'
import Card from '../components/ui/Card'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('Workspace profile')
  const [saved, setSaved] = useState(false)
  const [reminders, setReminders] = useState(true)
  const tabs = ['Workspace profile', 'Team members', 'Roles & permissions', 'Billing preferences', 'Notifications', 'API & integrations']
  return <div className="resource-page settings-page">
    <div className="page-heading resource-heading"><div><p className="eyebrow">Workspace / Settings</p><h1>Settings</h1><p className="heading-subtitle">Manage your workspace preferences and access.</p></div></div>
    <div className="settings-layout"><Card className="settings-nav">{tabs.map((tab) => <button key={tab} onClick={() => setActiveTab(tab)} className={`setting-tab ${activeTab === tab ? 'selected' : ''}`}>{tab}</button>)}</Card><Card className="settings-form"><h2>{activeTab}</h2><p className="form-description">Manage your {activeTab.toLowerCase()} preferences.</p>{activeTab === 'Workspace profile' ? <><div className="form-grid"><label>Workspace name<input defaultValue="Acme Corporation" /></label><label>Workspace email<input defaultValue="billing@acme.co" /></label><label>Default currency<select defaultValue="USD"><option>USD — US Dollar</option><option>EUR — Euro</option><option>GBP — Pound Sterling</option></select></label><label>Timezone<select defaultValue="UTC-05:00"><option>UTC-05:00 Eastern Time</option><option>UTC+00:00 Coordinated Universal Time</option></select></label></div><div className="form-divider" /><h2>Invoice preferences</h2><div className="toggle-row"><div><strong>Automatically send invoices</strong><span>Send confirmed invoices to customers by email.</span></div><button className="toggle on"><i /></button></div><div className="toggle-row"><div><strong>Payment reminders</strong><span>Remind customers before an invoice becomes overdue.</span></div><button className={`toggle ${reminders ? 'on' : ''}`} onClick={() => setReminders((value) => !value)}><i /></button></div><div className="form-actions"><button className="secondary-button" onClick={() => setSaved(false)}>Cancel</button><button className="primary-button" onClick={() => setSaved(true)}>Save changes</button></div>{saved && <p className="save-confirmation">Changes saved successfully.</p>}</> : <div className="settings-placeholder"><span>✦</span><strong>{activeTab} controls</strong><p>These workspace controls are ready to be configured.</p></div>}</Card></div>
  </div>
}
