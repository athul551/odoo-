import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import AuthShell, {
  AuthButton,
  AuthError,
  AuthField,
  AuthInput,
  AuthTextLink,
} from '../components/auth/AuthShell'
import { apiError } from '../lib/api'
import { landingPath, useAuth } from '../lib/auth'

const EMPTY = {
  first_name: '',
  last_name: '',
  organization_name: '',
  email: '',
  phone: '',
  password: '',
  password_confirm: '',
}

export default function SignupPage() {
  const { register, user } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={landingPath(user)} replace />

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (form.password !== form.password_confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await register({
        email: form.email,
        password: form.password,
        password_confirm: form.password_confirm,
        organization_name: form.organization_name,
        first_name: form.first_name || undefined,
        last_name: form.last_name || undefined,
        phone: form.phone || undefined,
        contact_email: form.email,
      })
      navigate('/portal', { replace: true })
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      eyebrow="Get started"
      title="Create your account"
      subtitle="Sign-up creates your organization and its first portal user. Staff accounts are provisioned by an admin."
      footer={
        <p>
          Already have an account? <AuthTextLink to="/login" className="text-sm">Sign in</AuthTextLink>
        </p>
      }
    >
      <form onSubmit={submit} className="space-y-5">
        <AuthError message={error} />

        <div className="grid gap-5 sm:grid-cols-2">
          <AuthField label="First name">
            <AuthInput autoComplete="given-name" value={form.first_name} onChange={set('first_name')} />
          </AuthField>
          <AuthField label="Last name">
            <AuthInput autoComplete="family-name" value={form.last_name} onChange={set('last_name')} />
          </AuthField>
        </div>

        <AuthField label="Organization" hint="The customer account your subscriptions belong to.">
          <AuthInput
            required
            autoComplete="organization"
            value={form.organization_name}
            onChange={set('organization_name')}
            placeholder="Acme Ltd"
          />
        </AuthField>

        <div className="grid gap-5 sm:grid-cols-2">
          <AuthField label="Work email">
            <AuthInput
              type="email"
              required
              autoComplete="email"
              value={form.email}
              onChange={set('email')}
              placeholder="you@company.com"
            />
          </AuthField>
          <AuthField label="Phone" hint="Optional">
            <AuthInput type="tel" autoComplete="tel" value={form.phone} onChange={set('phone')} />
          </AuthField>
        </div>

        <AuthField
          label="Password"
          hint="At least 9 characters, with an uppercase letter, a lowercase letter and a special character."
        >
          <AuthInput
            type="password"
            required
            autoComplete="new-password"
            value={form.password}
            onChange={set('password')}
          />
        </AuthField>

        <AuthField label="Confirm password">
          <AuthInput
            type="password"
            required
            autoComplete="new-password"
            value={form.password_confirm}
            onChange={set('password_confirm')}
          />
        </AuthField>

        <AuthButton type="submit" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'}
        </AuthButton>

        <p className="text-xs leading-relaxed text-faint">
          By creating an account you agree to keep your billing data accurate. Nothing is invoiced
          without a billing run you can preview first.
        </p>
      </form>
    </AuthShell>
  )
}
