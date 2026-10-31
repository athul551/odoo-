import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import DashboardPage from './pages/DashboardPage'
import NotFoundPage from './pages/NotFoundPage'
import ResourcePage from './pages/ResourcePage'
import ReportsPage from './pages/ReportsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/customers" element={<ResourcePage resource="customers" />} />
        <Route path="/products" element={<ResourcePage resource="products" />} />
        <Route path="/plans" element={<ResourcePage resource="plans" />} />
        <Route path="/quotations" element={<ResourcePage resource="quotations" />} />
        <Route path="/subscriptions" element={<ResourcePage resource="subscriptions" />} />
        <Route path="/invoices" element={<ResourcePage resource="invoices" />} />
        <Route path="/payments" element={<ResourcePage resource="payments" />} />
        <Route path="/discounts" element={<ResourcePage resource="discounts" />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
