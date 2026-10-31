import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="dark-page grid min-h-screen place-items-center px-6">
      <div className="text-center">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-faint">404</p>
        <h1 className="mt-3 text-4xl font-light tracking-tight text-paper">Page not found</h1>
        <p className="mt-2 text-sm text-muted">
          That route does not exist in this workspace.
        </p>
        <Link
          to="/"
          className="mt-6 inline-block rounded-panel border border-ink-600 px-4 py-2 text-sm text-paper transition hover:border-accent hover:text-accent"
        >
          Return to the console
        </Link>
      </div>
    </div>
  )
}
