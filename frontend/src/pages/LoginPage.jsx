import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import Button from '../components/ui/Button'
import { ErrorBox } from '../components/ui/Feedback'
import { Field, TextInput } from '../components/ui/Form'
import { apiError } from '../lib/api'
import { useAuth } from '../lib/auth'

export default function LoginPage() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(email, password)
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      const status = err.response?.status
      if (status === 401) {
        setError('Wrong email or password.')
      } else if (status === 429) {
        setError('Too many sign-in attempts. Wait a minute and try again.')
      } else {
        setError(apiError(err))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-base px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-2xl font-bold tracking-tight text-primary">Brightloop</p>
          <p className="mt-1.5 text-sm text-muted">Subscription management</p>
        </div>

        <form
          onSubmit={submit}
          className="space-y-6 rounded-xl border border-line bg-panel p-8"
        >
          <ErrorBox message={error} />
          <Field label="Email">
            <TextInput
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </Field>
          <Field label="Password">
            <TextInput
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Button type="submit" size="lg" className="w-full" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <div className="mt-6 space-y-1.5 text-center text-xs text-muted">
          <p>
            Need an account? Run{' '}
            <code className="rounded bg-raised px-1.5 py-0.5 text-secondary">
              manage.py createsuperuser
            </code>{' '}
            in the backend.
          </p>
          <p>
            Forgot the password?{' '}
            <code className="rounded bg-raised px-1.5 py-0.5 text-secondary">
              manage.py changepassword you@example.com
            </code>
          </p>
        </div>
      </div>
    </div>
  )
}
