import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return <div className="p-10">Page not found. <Link className="text-indigo-600" to="/">Return home</Link></div>
}
