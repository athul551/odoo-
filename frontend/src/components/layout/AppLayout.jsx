import { Outlet } from 'react-router-dom'

export default function AppLayout() {
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-6 py-12">
      <header className="mb-10 flex items-center justify-between">
        <span className="text-xl font-bold tracking-tight text-indigo-600">Brightloop</span>
        <span className="text-sm text-slate-500">Subscription Management</span>
      </header>
      <Outlet />
    </main>
  )
}
