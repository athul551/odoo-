import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

const NAV_GROUPS = [
  {
    label: 'Operations',
    items: [
      { to: '/', label: 'Dashboard', end: true },
      { to: '/customers', label: 'Customers' },
      { to: '/subscriptions', label: 'Subscriptions' },
      { to: '/billing', label: 'Billing' },
    ],
  },
  {
    label: 'Catalog',
    items: [{ to: '/catalog', label: 'Products & plans' }],
  },
  {
    label: 'System',
    items: [{ to: '/database', label: 'Database', admin: true }],
  },
]

function railItemClass({ isActive }) {
  return `relative block rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive
      ? 'bg-accent/15 text-primary'
      : 'text-secondary hover:bg-raised hover:text-primary'
  }`
}

const railActiveBar = (
  <span className="absolute -left-3 top-1/2 h-6 w-1 -translate-y-1/2 rounded-full bg-accent" />
)

export default function AppLayout() {
  const { user, isAdmin, logout } = useAuth()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)

  const signOut = async () => {
    setMenuOpen(false)
    await logout()
    navigate('/login')
  }

  const groups = NAV_GROUPS.filter(
    (group) => !group.items.every((item) => item.admin) || isAdmin,
  )

  const rail = (
    <nav className="flex flex-col gap-6 px-3 py-4">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
            {group.label}
          </p>
          <div className="flex flex-col gap-0.5">
            {group.items
              .filter((item) => !item.admin || isAdmin)
              .map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={() => setMenuOpen(false)}
                  className={railItemClass}
                >
                  {({ isActive }) => (
                    <>
                      {isActive && railActiveBar}
                      {item.label}
                    </>
                  )}
                </NavLink>
              ))}
          </div>
        </div>
      ))}
    </nav>
  )

  return (
    <div className="min-h-screen bg-base">
      {/* universal top nav */}
      <header className="sticky top-0 z-30 border-b border-line bg-base/95 backdrop-blur">
        <div className="flex h-16 items-center gap-4 px-4 lg:px-6">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="rounded-lg border border-line px-3 py-2 text-sm text-secondary hover:bg-raised hover:text-primary lg:hidden"
            aria-label="Toggle menu"
          >
            ☰
          </button>

          <div className="flex items-baseline gap-2">
            <span className="text-base font-bold tracking-tight text-primary">Brightloop</span>
            <span className="hidden text-xs text-muted sm:inline">Subscription management</span>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <span className="hidden rounded-full border border-line px-3 py-1 text-xs text-secondary sm:inline">
              {user?.customer?.name ?? user?.role_display ?? user?.role}
            </span>
            <span className="truncate text-xs text-muted">{user?.email}</span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-lg border border-line px-3 py-2 text-xs text-secondary transition hover:bg-raised hover:text-primary"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px]">
        {/* contextual left rail — desktop */}
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-60 shrink-0 border-r border-line lg:block">
          {rail}
        </aside>

        {/* left rail — mobile drawer */}
        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-base/70 backdrop-blur-sm"
              onClick={() => setMenuOpen(false)}
              aria-hidden="true"
            />
            <aside className="absolute left-0 top-0 h-full w-72 border-r border-line bg-base shadow-2xl">
              <div className="flex h-16 items-center justify-between border-b border-line px-4">
                <span className="text-base font-bold tracking-tight text-primary">Brightloop</span>
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg px-2 py-1 text-muted hover:bg-raised"
                  aria-label="Close menu"
                >
                  ✕
                </button>
              </div>
              <div className="h-[calc(100%-4rem)] overflow-y-auto">{rail}</div>
            </aside>
          </div>
        )}

        <main className="min-w-0 flex-1 px-4 py-10 lg:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
