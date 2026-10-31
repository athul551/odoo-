import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { Loading } from './components/ui/Feedback'
import BillingPage from './pages/BillingPage'
import CatalogPage from './pages/CatalogPage'
import CustomersPage from './pages/CustomersPage'
import DashboardPage from './pages/DashboardPage'
import DatabasePage from './pages/DatabasePage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import SubscriptionDetailPage from './pages/SubscriptionDetailPage'
import SubscriptionsPage from './pages/SubscriptionsPage'
import { useAuth } from './lib/auth'

function RequireAuth({ children }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) {
    return (
      <div className="mx-auto max-w-md p-10">
        <Loading label="Checking session…" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return children
}

function RequireAdmin({ children }) {
  const { isAdmin } = useAuth()
  return isAdmin ? children : <Navigate to="/" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/subscriptions" element={<SubscriptionsPage />} />
        <Route path="/subscriptions/:id" element={<SubscriptionDetailPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route
          path="/database"
          element={
            <RequireAdmin>
              <DatabasePage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
