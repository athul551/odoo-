import { useState } from 'react'
import { Link } from 'react-router-dom'
import AuthShell, {
  AuthButton,
  AuthError,
  AuthField,
  AuthInput,
  AuthNotice,
  AuthTextLink,
} from '../components/auth/AuthShell'
import api, { apiError } from '../lib/api'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/auth/password/reset/', { email })
      setSent(true)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Password reset"
      title="Forgot your password?"
      subtitle="Enter the email on your account. If it exists, we send a single-use reset link."
      footer={
        <p>
          Remembered it? <AuthTextLink to="/login">Back to sign in</AuthTextLink>
        </p>
      }
    >
      {sent ? (
        <div className="space-y-5">
          <AuthNotice message="If that email has an account, a reset link is on its way." />
          <p className="text-sm leading-relaxed text-muted">
            The link expires after a short while and can only be used once. Check your spam folder
            if it does not arrive.
          </p>
          <Link
            to="/login"
            className="block text-center text-sm font-medium text-accent hover:text-accent-hover"
          >
            Return to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          <AuthError message={error} />
          <AuthField label="Email">
            <AuthInput
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
          </AuthField>
          <AuthButton type="submit" disabled={busy}>
            {busy ? 'Sending…' : 'Send reset link'}
          </AuthButton>
        </form>
      )}
    </AuthShell>
  )
}
