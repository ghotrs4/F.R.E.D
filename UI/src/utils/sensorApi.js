// API functions for sensor data
import { apiUrl } from './apiBase'

const API_BASE_URL = apiUrl('/api')

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

/**
 * Calibrate MQ sensor max values to current live readings.
 * @returns {Promise<{message: string, updatedMaxValues: Record<number, number>}>}
 */
export async function calibrateMqSensors() {
  const response = await fetch(`${API_BASE_URL}/sensor/mq/calibrate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const errorMessage = payload?.error || `HTTP error! status: ${response.status}`
    throw new Error(errorMessage)
  }

  return payload
}
