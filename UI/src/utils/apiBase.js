const trimTrailingSlash = (value) => String(value || '').replace(/\/$/, '')

const resolveDefaultApiBaseUrl = () => {
  if (import.meta.env.DEV) return ''
  if (typeof window === 'undefined') return ''

  return window.location.origin
}

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || resolveDefaultApiBaseUrl()
)

export const apiUrl = (path = '') => {
  if (!path) return API_BASE_URL
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}
