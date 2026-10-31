import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/customers', label: 'Customers' },
  { to: '/catalog', label: 'Catalog' },
  { to: '/subscriptions', label: 'Subscriptions' },
  { to: '/billing', label: 'Billing' },
  { to: '/database', label: 'Database', admin: true },
]

function navClass({ isActive }) {
  return `block shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
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
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 lg:flex-row lg:px-8">
        <aside className="lg:w-56 lg:shrink-0">
          <div className="mb-4">
            <p className="text-lg font-bold tracking-tight text-indigo-600">Brightloop</p>
            <p className="text-xs text-slate-400">Backend console</p>
          </div>

          <nav className="flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
            {NAV.filter((item) => !item.admin || isAdmin).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-6 hidden rounded-xl border border-slate-200 bg-white p-3 lg:block">
            <p className="truncate text-xs font-medium text-slate-700">{user?.email}</p>
            <p className="mt-0.5 text-xs capitalize text-slate-400">{user?.role}</p>
            <button
              type="button"
              onClick={signOut}
              className="mt-3 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <div className="mb-4 flex items-center justify-between gap-3 lg:hidden">
            <span className="truncate text-xs text-slate-400">{user?.email}</span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-600"
            >
              Sign out
            </button>
          </div>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
