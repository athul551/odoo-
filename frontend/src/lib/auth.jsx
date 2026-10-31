import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api from './api'

const AuthContext = createContext(null)

const KEYS = {
  access: 'brightloop_access_token',
  refresh: 'brightloop_refresh_token',
  user: 'brightloop_user',
}

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(KEYS.user))
  } catch {
    return null
  }
}

function storeSession(data) {
  localStorage.setItem(KEYS.access, data.access)
  localStorage.setItem(KEYS.refresh, data.refresh)
  localStorage.setItem(KEYS.user, JSON.stringify(data.user))
}

/** Where a signed-in user belongs: customers get the portal, staff the console. */
export function landingPath(user) {
  return user?.role === 'customer' ? '/portal' : '/'
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(KEYS.access)) {
      setReady(true)
      return
    }
    api
      .get('/auth/me/')
      .then(({ data }) => {
        setUser(data)
        localStorage.setItem(KEYS.user, JSON.stringify(data))
      })
      .catch(() => {
        // A dead token is handled by the 401 interceptor.
      })
      .finally(() => setReady(true))
  }, [])

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/token/', { email, password })
    storeSession(data)
    setUser(data.user)
    return data.user
  }, [])

  const register = useCallback(async (payload) => {
    const { data } = await api.post('/auth/register/', payload)
    storeSession(data)
    setUser(data.user)
    return data.user
  }, [])

  const updateProfile = useCallback(async (payload) => {
    const { data } = await api.patch('/auth/me/', payload)
    setUser(data)
    localStorage.setItem(KEYS.user, JSON.stringify(data))
    return data
  }, [])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem(KEYS.refresh)
    if (refresh) {
      try {
        await api.post('/auth/logout/', { refresh })
      } catch {
        // An already-dead token still means "signed out".
      }
    }
    Object.values(KEYS).forEach((key) => localStorage.removeItem(key))
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      ready,
      login,
      register,
      updateProfile,
      logout,
      isAdmin: user?.role === 'admin',
      isStaff: user?.role === 'admin' || user?.role === 'staff',
      isCustomer: user?.role === 'customer',
    }),
    [user, ready, login, register, updateProfile, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
