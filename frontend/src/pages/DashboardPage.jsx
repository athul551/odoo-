import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api from '../lib/api'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'

const demoSummary = {
  active_subscriptions: 1284,
  mrr: '48260.00',
  invoiced_total: '125480.00',
  collected_total: '113920.00',
  outstanding: { count: 18, amount: '11560.00' },
  overdue: { count: 7, amount: '4280.00' },
}

const revenue = [
  { month: 'May', revenue: 28000, collected: 24500 },
  { month: 'Jun', revenue: 34200, collected: 30100 },
  { month: 'Jul', revenue: 31800, collected: 28600 },
  { month: 'Aug', revenue: 40500, collected: 36100 },
  { month: 'Sep', revenue: 44700, collected: 40300 },
  { month: 'Oct', revenue: 51200, collected: 46700 },
]

const payments = [
  ['INV-2026-0842', 'Acme Corporation', 'Oct 28, 2026', '$2,400.00', 'Paid'],
  ['INV-2026-0837', 'Northstar Labs', 'Oct 27, 2026', '$1,850.00', 'Paid'],
  ['INV-2026-0831', 'Vantage Systems', 'Oct 26, 2026', '$4,200.00', 'Pending'],
  ['INV-2026-0824', 'Solstice Studio', 'Oct 24, 2026', '$980.00', 'Paid'],
]

function money(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value))
}

function StatCard({ label, value, change, note, icon, tone = 'blue' }) {
  return <Card className="stat-card">
    <div className={`stat-icon ${tone}`}>{icon}</div>
    <div className="stat-label">{label}<span className="stat-menu">•••</span></div>
    <div className="stat-value">{value}</div>
    <div className="stat-foot"><span className="trend-up">↗ {change}</span><span>{note}</span></div>
  </Card>
}

export default function DashboardPage() {
  const [summary, setSummary] = useState(demoSummary)
  const [apiUnavailable, setApiUnavailable] = useState(false)

  useEffect(() => {
    api.get('/reporting/summary/').then(({ data }) => setSummary(data)).catch(() => setApiUnavailable(true))
  }, [])

  return <div className="dashboard">
    {apiUnavailable && <div className="api-notice">Showing sample data while the reporting service is unavailable.</div>}
    <div className="page-heading">
      <div><p className="eyebrow">Saturday, October 31, 2026</p><h1>Good morning, Jordan <span>✦</span></h1><p className="heading-subtitle">Here’s what’s happening across your subscriptions today.</p></div>
      <div className="heading-actions"><Link className="secondary-button" to="/reports">↥ Export report</Link><Link className="primary-button" to="/subscriptions">＋ New subscription</Link></div>
    </div>

    <div className="filter-row"><div className="period-tabs"><button className="selected">Overview</button><button>Last 30 days</button><button>Last 12 months</button></div><button className="date-filter">October 01 – October 31, 2026 <span>⌄</span></button></div>

    <div className="stats-grid">
      <StatCard label="Monthly recurring revenue" value={money(summary.mrr)} change="8.4%" note="vs last month" icon="↗" />
      <StatCard label="Active subscriptions" value={summary.active_subscriptions.toLocaleString()} change="12.2%" note="vs last month" icon="↻" tone="green" />
      <StatCard label="Total collected" value={money(summary.collected_total)} change="5.6%" note="vs last month" icon="$" tone="purple" />
      <StatCard label="Outstanding payments" value={money(summary.outstanding.amount)} change="2.1%" note="vs last month" icon="◷" tone="orange" />
    </div>

    <div className="dashboard-grid">
      <Card className="revenue-card">
        <div className="card-heading"><div><h2>Revenue overview</h2><p>Track your revenue and collections over time</p></div><div className="legend"><span><i className="legend-dot blue-dot" />Revenue</span><span><i className="legend-dot pale-dot" />Collected</span></div></div>
        <div className="chart-wrap"><ResponsiveContainer width="100%" height={250}><AreaChart data={revenue} margin={{ top: 10, right: 12, left: -18, bottom: 0 }}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#315e91" stopOpacity=".16" /><stop offset="100%" stopColor="#315e91" stopOpacity="0" /></linearGradient></defs><XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: '#8a96a5', fontSize: 12 }} /><YAxis axisLine={false} tickLine={false} tick={{ fill: '#8a96a5', fontSize: 11 }} tickFormatter={(value) => `$${value / 1000}k`} /><Tooltip formatter={(value) => money(value)} contentStyle={{ border: '1px solid #e3e7ed', borderRadius: 8, boxShadow: '0 6px 20px #202a3514' }} /><Area type="monotone" dataKey="revenue" stroke="#315e91" strokeWidth={2.5} fill="url(#revenueFill)" /><Area type="monotone" dataKey="collected" stroke="#9bb7d5" strokeWidth={2} fill="none" /></AreaChart></ResponsiveContainer></div>
      </Card>
      <Card className="subscription-card">
        <div className="card-heading"><div><h2>Subscription health</h2><p>Current lifecycle breakdown</p></div><Link className="more-button" to="/subscriptions" aria-label="View subscriptions">•••</Link></div>
        <div className="health-ring"><div className="ring-center"><strong>1,284</strong><span>Total active</span></div></div>
        <div className="health-legend"><span><i className="status-dot active-dot" />Active <b>1,104</b></span><span><i className="status-dot paused-dot" />Paused <b>92</b></span><span><i className="status-dot trial-dot" />Trial <b>88</b></span></div>
      </Card>
    </div>

    <div className="dashboard-grid lower-grid">
      <Card className="payments-card"><div className="card-heading"><div><h2>Recent payments</h2><p>Latest transactions from your customers</p></div><Link to="/payments">View all <span>→</span></Link></div><div className="table-wrap"><table><thead><tr><th>Invoice</th><th>Customer</th><th>Date</th><th>Amount</th><th>Status</th></tr></thead><tbody>{payments.map(([invoice, customer, date, amount, status]) => <tr key={invoice}><td className="invoice-number">{invoice}</td><td>{customer}</td><td className="muted">{date}</td><td className="amount">{amount}</td><td><span className={`status-badge ${status.toLowerCase()}`}>{status}</span></td></tr>)}</tbody></table></div></Card>
      <Card className="attention-card"><div className="card-heading"><div><h2>Needs attention</h2><p>Items requiring your review</p></div><span className="attention-count">{summary.overdue.count + summary.outstanding.count}</span></div><div className="attention-list"><div><span className="attention-icon red">!</span><p><strong>{summary.overdue.count} overdue invoices</strong><span>Past their payment due date</span></p><button>→</button></div><div><span className="attention-icon amber">◷</span><p><strong>{summary.outstanding.count} outstanding payments</strong><span>Awaiting customer payment</span></p><button>→</button></div><div><span className="attention-icon blue">↻</span><p><strong>6 renewals this week</strong><span>Subscriptions coming up</span></p><button>→</button></div></div></Card>
    </div>
  </div>
}
