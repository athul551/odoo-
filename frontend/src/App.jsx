import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import PortalLayout from './components/layout/PortalLayout'
import { Loading } from './components/ui/Feedback'
import { useAuth } from './lib/auth'
import BillingPage from './pages/BillingPage'
import CatalogPage from './pages/CatalogPage'
import CustomersPage from './pages/CustomersPage'
import DashboardPage from './pages/DashboardPage'
import DatabasePage from './pages/DatabasePage'
import DiscountsPage from './pages/DiscountsPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import ReportingPage from './pages/ReportingPage'
import PrintInvoicePage from './pages/PrintInvoicePage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import SignupPage from './pages/SignupPage'
import SubscriptionDetailPage from './pages/SubscriptionDetailPage'
import SubscriptionsPage from './pages/SubscriptionsPage'
import UsersPage from './pages/UsersPage'
import AccountPage from './pages/portal/AccountPage'
import PortalInvoicesPage from './pages/portal/InvoicesPage'
import PortalOverviewPage from './pages/portal/OverviewPage'
import PortalSubscriptionsPage from './pages/portal/SubscriptionsPage'

function LoadingScreen() {
  return (
    <div className="dark-page grid min-h-screen place-items-center">
      <div className="text-muted">
        <Loading label="Checking session…" />
      </div>
    </div>
  )
}

function RequireStaff({ children }) {
  const { user, ready, isStaff } = useAuth()
  const location = useLocation()
  if (!ready) return <LoadingScreen />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (!isStaff) return <Navigate to="/portal" replace />
  return children
}

function RequireCustomer({ children }) {
  const { user, ready, isCustomer } = useAuth()
  const location = useLocation()
  if (!ready) return <LoadingScreen />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (!isCustomer) return <Navigate to="/" replace />
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
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/print/invoice/:id"
        element={
          <RequireStaff>
            <PrintInvoicePage />
          </RequireStaff>
        }
      />

      <Route
        element={
          <RequireStaff>
            <AppLayout />
          </RequireStaff>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/subscriptions" element={<SubscriptionsPage />} />
        <Route path="/subscriptions/:id" element={<SubscriptionDetailPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/reporting" element={<ReportingPage />} />
        <Route
          path="/discounts"
          element={
            <RequireAdmin>
              <DiscountsPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/database"
          element={
            <RequireAdmin>
              <DatabasePage />
            </RequireAdmin>
          }
        />
      </Route>

      <Route
        path="/portal"
        element={
          <RequireCustomer>
            <PortalLayout />
          </RequireCustomer>
        }
      >
        <Route index element={<PortalOverviewPage />} />
        <Route path="subscriptions" element={<PortalSubscriptionsPage />} />
        <Route path="invoices" element={<PortalInvoicesPage />} />
        <Route path="account" element={<AccountPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
