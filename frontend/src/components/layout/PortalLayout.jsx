import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

const NAV = [
  { to: '/portal', label: 'Overview', end: true },
  { to: '/portal/subscriptions', label: 'Subscriptions' },
  { to: '/portal/invoices', label: 'Invoices' },
  { to: '/portal/account', label: 'Account' },
]

function navClass({ isActive }) {
  return `relative rounded-md px-3 py-2 text-sm font-medium transition duration-150 ease-calm ${
    isActive
      ? 'bg-accent-soft text-accent'
      : 'text-muted hover:bg-ink-700 hover:text-paper'
  }`
}

export default function PortalLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const signOut = async () => {
    await logout()
    navigate('/login')
  }

  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email

  return (
    <div className="dark-page min-h-screen">
      <header className="border-b border-ink-600 bg-ink-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-bold text-ink-950">
              B
            </span>
            <div>
              <p className="text-sm font-semibold tracking-wide text-paper">Brightloop</p>
              <p className="text-xs text-faint">Customer portal</p>
            </div>
          </div>

          <nav className="order-3 flex w-full gap-1 overflow-x-auto md:order-2 md:w-auto md:flex-1 md:justify-center">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="order-2 ml-auto flex items-center gap-3 md:order-3">
            <div className="text-right">
              <p className="max-w-[180px] truncate text-xs font-medium text-paper">{displayName}</p>
              <p className="text-[11px] text-faint">{user?.customer?.name ?? 'Portal user'}</p>
            </div>
            <button
              type="button"
              onClick={signOut}
              className="rounded-md border border-ink-600 px-3 py-1.5 text-xs text-muted transition hover:border-ink-500 hover:text-paper"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-6xl px-6 pb-10 text-xs text-faint">
        Brightloop · invoices and subscriptions for {user?.customer?.name ?? 'your organization'}
      </footer>
    </div>
  )
}
