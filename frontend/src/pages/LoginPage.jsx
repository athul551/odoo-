import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import AuthShell, {
  AuthButton,
  AuthError,
  AuthField,
  AuthInput,
  AuthTextLink,
} from '../components/auth/AuthShell'
import { apiError } from '../lib/api'
import { landingPath, useAuth } from '../lib/auth'

export default function LoginPage() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={landingPath(user)} replace />

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const signedIn = await login(email, password)
      navigate(location.state?.from ?? landingPath(signedIn), { replace: true })
    } catch (err) {
      const status = err.response?.status
      if (status === 401) setError('Wrong email or password.')
      else if (status === 429) setError('Too many sign-in attempts. Wait a minute and try again.')
      else setError(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in"
      subtitle="Use your work email. Customers land in the portal; staff land in the console."
      footer={
        <p>
          New to Brightloop?{' '}
          <AuthTextLink to="/signup" className="text-sm">
            Create an account
          </AuthTextLink>
        </p>
      }
    >
      <form onSubmit={submit} className="space-y-5">
        <AuthError message={error} />

        <AuthField label="Email">
          <AuthInput
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </AuthField>

        <AuthField
          label="Password"
          action={<AuthTextLink to="/forgot-password">Forgot password?</AuthTextLink>}
        >
          <AuthInput
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </AuthField>

        <AuthButton type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </AuthButton>

        <p className="text-center text-xs text-faint">Your data stays inside your organization.</p>
      </form>
    </AuthShell>
  )
}
