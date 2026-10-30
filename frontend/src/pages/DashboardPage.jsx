import Card from '../components/ui/Card'

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Welcome to Brightloop</h1>
        <p className="mt-2 text-slate-600">The subscription-management platform foundation is ready.</p>
      </div>
      <Card>
        <h2 className="font-semibold">Next modules</h2>
        <p className="mt-2 text-sm text-slate-600">Products, plans, customers, quotations, subscriptions, billing, payments, discounts, and financial reports will be added here.</p>
      </Card>
    </div>
  )
}
