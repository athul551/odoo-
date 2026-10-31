import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'

const api = axios.create({ baseURL: API_BASE_URL })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('brightloop_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && localStorage.getItem('brightloop_access_token')) {
      localStorage.removeItem('brightloop_access_token')
      localStorage.removeItem('brightloop_refresh_token')
      localStorage.removeItem('brightloop_user')
      if (!window.location.pathname.startsWith('/login')) window.location.assign('/login')
    }
    return Promise.reject(error)
  },
)

/**
 * Flatten the API's one error shape ({"errors": {field: [msg]}}) into a line a
 * human can read. Every page renders this the same way.
 */
export function apiError(error) {
  if (!error) return 'Unknown error'
  const data = error.response?.data
  if (!data) return error.message || 'Network error — is the API running?'

  const lines = []
  const walk = (value, prefix = '') => {
    if (value == null) return
    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, prefix))
      return
    }
    if (typeof value === 'object') {
      Object.entries(value).forEach(([key, item]) => {
        walk(item, prefix ? `${prefix}.${key}` : key)
      })
      return
    }
    lines.push(prefix ? `${prefix}: ${value}` : String(value))
  }
  walk(data.errors ?? data)

  if (!lines.length) return `Request failed (${error.response?.status ?? 'network'})`
  return lines.join(' · ')
}

export const listOf = (data) => (Array.isArray(data) ? data : data?.results ?? [])

export default api
