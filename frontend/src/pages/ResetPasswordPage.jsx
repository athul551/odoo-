import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import AuthShell, {
  AuthButton,
  AuthError,
  AuthField,
  AuthInput,
  AuthNotice,
  AuthTextLink,
} from '../components/auth/AuthShell'
import api, { apiError } from '../lib/api'

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await api.post('/auth/password/reset/confirm/', {
        uid,
        token,
        new_password: password,
        new_password_confirm: confirm,
      })
      setDone(true)
    } catch (err) {
      setError(apiError(err))
    } finally {
      setBusy(false)
    }
  }

  if (!uid || !token) {
    return (
      <AuthShell
        eyebrow="Password reset"
        title="This link is incomplete"
        subtitle="Reset links carry a user id and a single-use token."
        footer={
          <p>
            <AuthTextLink to="/forgot-password">Request a new link</AuthTextLink>
          </p>
        }
      >
        <AuthError message="The link is missing its uid or token. Request a fresh reset email." />
      </AuthShell>
    )
  }

  return (
    <AuthShell
      eyebrow="Password reset"
      title="Choose a new password"
      subtitle="The reset token is single-use and expires; changing the password signs out every other session."
      footer={
        <p>
          <AuthTextLink to="/login">Back to sign in</AuthTextLink>
        </p>
      }
    >
      {done ? (
        <div className="space-y-5">
          <AuthNotice message="Password changed. You can sign in with it now." />
          <Link
            to="/login"
            className="block text-center text-sm font-medium text-accent hover:text-accent-hover"
          >
            Go to sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          <AuthError message={error} />
          <AuthField
            label="New password"
            hint="At least 9 characters, with an uppercase letter, a lowercase letter and a special character."
          >
            <AuthInput
              type="password"
              required
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </AuthField>
          <AuthField label="Confirm new password">
            <AuthInput
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </AuthField>
          <AuthButton type="submit" disabled={busy}>
            {busy ? 'Changing…' : 'Change password'}
          </AuthButton>
        </form>
      )}
    </AuthShell>
  )
}
