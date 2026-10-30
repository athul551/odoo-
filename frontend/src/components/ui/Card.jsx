export default function Card({ children, className = '' }) {
  return <section className={`rounded-xl border border-slate-200 bg-white p-6 shadow-sm ${className}`}>{children}</section>
}
