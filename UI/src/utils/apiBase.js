const trimTrailingSlash = (value) => String(value || '').replace(/\/$/, '')

const resolveDefaultApiBaseUrl = () => {
  if (import.meta.env.DEV) return ''
  if (typeof window === 'undefined') return ''

  // Prevent mixed-content requests when UI is served over HTTPS.
  if (window.location.protocol === 'https:') {
    return ''
  }

  return `http://${window.location.hostname}:5000`
}

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || resolveDefaultApiBaseUrl()
)

export const apiUrl = (path = '') => {
  if (!path) return API_BASE_URL
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}
