import Card from '../components/ui/Card'

const reports = [
  ['Revenue report', 'Understand revenue, collections, and growth by period.', '$125,480', '+8.4%', 'blue'],
  ['Active subscriptions', 'See current subscription volume and lifecycle health.', '1,284', '+12.2%', 'green'],
  ['Payment report', 'Review payment methods, collected totals, and trends.', '$113,920', '+5.6%', 'purple'],
  ['Collections report', 'Prioritize outstanding and overdue invoices.', '$15,840', '25 items', 'orange'],
]

export default function ReportsPage() {
  return <div className="resource-page reports-page">
    <div className="page-heading resource-heading"><div><p className="eyebrow">Workspace / Reports</p><h1>Reports</h1><p className="heading-subtitle">Finance and subscription insights for your business.</p></div><button className="secondary-button">↥ Export report</button></div>
    <div className="report-filter"><div className="period-tabs"><button className="selected">This month</button><button>Last month</button><button>This quarter</button><button>Custom range</button></div><button className="date-filter">October 01 – October 31, 2026 <span>⌄</span></button></div>
    <div className="report-grid">{reports.map(([title, description, value, change, tone]) => <Card key={title} className="report-card"><div className={`report-icon ${tone}`}>◫</div><h2>{title}</h2><p>{description}</p><div className="report-value">{value}</div><span className="report-change">{change}</span><button className="report-link">View report →</button></Card>)}</div>
    <Card className="report-table-card"><div className="card-heading"><div><h2>Collections overview</h2><p>Invoices that need follow-up</p></div><button className="filter-button">Download CSV</button></div><div className="empty-report"><span>◫</span><strong>Detailed report views are ready</strong><p>Choose a report above to explore the underlying data.</p></div></Card>
  </div>
}
