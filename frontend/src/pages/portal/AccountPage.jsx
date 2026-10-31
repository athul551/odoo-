import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Panel } from '../../components/portal/ui'
import api, { apiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dateOnly } from '../../lib/format'

const inputClass =
  'h-12 w-full rounded-panel border border-ink-600 bg-ink-900 px-3 text-sm text-paper placeholder:text-faint dark-focus disabled:opacity-40'

function Field({ label, hint, error, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-faint">
        {label}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-faint">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  )
}

function Notice({ message }) {
  if (!message) return null
  return (
    <div className="rounded-panel border border-ok/40 bg-ok/10 px-4 py-3 text-sm text-ok">
      {message}
    </div>
  )
}

function Problem({ message }) {
  if (!message) return null
  return (
    <div className="rounded-panel border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
      {message}
    </div>
  )
}

export default function AccountPage() {
  const { user, updateProfile, logout } = useAuth()
  const navigate = useNavigate()

  const [profile, setProfile] = useState({
    first_name: user?.first_name ?? '',
    last_name: user?.last_name ?? '',
  })
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileError, setProfileError] = useState('')
  const [profileNotice, setProfileNotice] = useState('')

  const [passwords, setPasswords] = useState({
    current_password: '',
    new_password: '',
    new_password_confirm: '',
  })
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [passwordNotice, setPasswordNotice] = useState('')

  const saveProfile = async (event) => {
    event.preventDefault()
    setProfileBusy(true)
    setProfileError('')
    setProfileNotice('')
    try {
      await updateProfile(profile)
      setProfileNotice('Profile updated.')
    } catch (err) {
      setProfileError(apiError(err))
    } finally {
      setProfileBusy(false)
    }
  }

  const changePassword = async (event) => {
    event.preventDefault()
    setPasswordBusy(true)
    setPasswordError('')
    setPasswordNotice('')
    if (passwords.new_password !== passwords.new_password_confirm) {
      setPasswordError('New passwords do not match.')
      setPasswordBusy(false)
      return
    }
    try {
      await api.post('/auth/password/change/', passwords)
      setPasswords({ current_password: '', new_password: '', new_password_confirm: '' })
      setPasswordNotice('Password changed. Other sessions were signed out.')
    } catch (err) {
      setPasswordError(apiError(err))
    } finally {
      setPasswordBusy(false)
    }
  }

  const signOut = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-paper">Account</h1>
          <p className="mt-2 text-sm text-muted">Your profile, organization and credentials.</p>
        </div>
        <button
          type="button"
          onClick={signOut}
          className="h-11 rounded-panel border border-ink-600 px-4 text-sm text-muted transition hover:text-paper"
        >
          Sign out
        </button>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Profile" subtitle="Shown on invoices and in the staff console.">
          <form onSubmit={saveProfile} className="space-y-4">
            <Problem message={profileError} />
            <Notice message={profileNotice} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First name">
                <input
                  className={inputClass}
                  value={profile.first_name}
                  onChange={(event) =>
                    setProfile({ ...profile, first_name: event.target.value })
                  }
                />
              </Field>
              <Field label="Last name">
                <input
                  className={inputClass}
                  value={profile.last_name}
                  onChange={(event) =>
                    setProfile({ ...profile, last_name: event.target.value })
                  }
                />
              </Field>
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={profileBusy}
                className="h-11 rounded-panel bg-accent px-5 text-sm font-semibold text-ink-950 transition hover:bg-accent-hover disabled:opacity-40"
              >
                {profileBusy ? 'Saving…' : 'Save profile'}
              </button>
            </div>
          </form>
        </Panel>

        <Panel title="Organization" subtitle="Set at sign-up; contact us to change it.">
          <dl className="space-y-3 text-sm">
            {[
              ['Organization', user?.customer?.name ?? '—'],
              ['Email', user?.email ?? '—'],
              ['Role', user?.role_display ?? user?.role ?? '—'],
              ['Member since', dateOnly(user?.date_joined)],
            ].map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-4">
                <dt className="text-faint">{label}</dt>
                <dd className="text-right text-paper">{value}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <Panel
        title="Password"
        subtitle="At least 9 characters, with an uppercase letter, a lowercase letter and a special character."
      >
        <form onSubmit={changePassword} className="max-w-xl space-y-4">
          <Problem message={passwordError} />
          <Notice message={passwordNotice} />
          <Field label="Current password">
            <input
              type="password"
              autoComplete="current-password"
              required
              className={inputClass}
              value={passwords.current_password}
              onChange={(event) =>
                setPasswords({ ...passwords, current_password: event.target.value })
              }
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New password">
              <input
                type="password"
                autoComplete="new-password"
                required
                className={inputClass}
                value={passwords.new_password}
                onChange={(event) =>
                  setPasswords({ ...passwords, new_password: event.target.value })
                }
              />
            </Field>
            <Field label="Confirm new password">
              <input
                type="password"
                autoComplete="new-password"
                required
                className={inputClass}
                value={passwords.new_password_confirm}
                onChange={(event) =>
                  setPasswords({ ...passwords, new_password_confirm: event.target.value })
                }
              />
            </Field>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={passwordBusy}
              className="h-11 rounded-panel bg-accent px-5 text-sm font-semibold text-ink-950 transition hover:bg-accent-hover disabled:opacity-40"
            >
              {passwordBusy ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  )
}
