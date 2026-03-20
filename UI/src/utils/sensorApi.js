// API functions for sensor data
const API_BASE_URL = `${(
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? '' : `http://${window.location.hostname}:5000`)
).replace(/\/$/, '')}/api`

/**
 * Fetch current sensor readings
 * @returns {Promise<{temperature: number, humidity: number, connected: boolean}>}
 */
export async function getSensorData() {
  try {
    const response = await fetch(`${API_BASE_URL}/sensor`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const data = await response.json()
    return data
  } catch (error) {
    console.error('Error fetching sensor data:', error)
    // Return default values with disconnected status on error
    return {
      temperature: 4.0,
      humidity: 50.0,
      connected: false
    }
  }
}
