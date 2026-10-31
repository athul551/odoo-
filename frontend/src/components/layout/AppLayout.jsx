import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/customers', label: 'Customers' },
  { to: '/catalog', label: 'Catalog' },
  { to: '/subscriptions', label: 'Subscriptions' },
  { to: '/billing', label: 'Billing' },
  { to: '/reporting', label: 'Reporting' },
  { to: '/discounts', label: 'Discounts', admin: true },
  { to: '/users', label: 'Users', admin: true },
  { to: '/database', label: 'Database', admin: true },
]

function navClass({ isActive }) {
  return `block shrink-0 border-l-2 px-3 py-2 text-sm font-medium transition duration-150 ease-calm ${
    isActive
      ? 'border-accent bg-accent-soft text-accent'
      : 'border-transparent text-muted hover:bg-ink-700 hover:text-paper'
  }`
}

export default function AppLayout() {
  const { user, isAdmin, logout } = useAuth()
  const navigate = useNavigate()

  const signOut = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="dark-page min-h-screen">
      <header className="sticky top-0 z-30 border-b border-ink-600 bg-ink-900/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-accent text-sm font-bold text-ink-950">
              B
            </span>
            <div>
              <p className="text-sm font-semibold tracking-wide text-paper">Brightloop</p>
              <p className="text-[11px] text-faint">Operations console</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="max-w-[220px] truncate text-xs font-medium text-paper">{user?.email}</p>
              <p className="text-[11px] capitalize text-faint">{user?.role}</p>
            </div>
            <button
              type="button"
              onClick={signOut}
              className="rounded-md border border-ink-600 px-3 py-1.5 text-xs text-muted transition hover:text-paper"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px] flex-col gap-8 px-6 py-8 lg:flex-row">
        <aside className="lg:w-56 lg:shrink-0">
          <nav className="flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
            {NAV.filter((item) => !item.admin || isAdmin).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
