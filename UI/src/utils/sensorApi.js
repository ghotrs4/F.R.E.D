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
      ambient_light_intensity: 0.0,
      auto_door_enabled: false,
      auto_door_lux_threshold: 0.0,
      auto_door_lux_trigger_offset: 50.0,
      connected: false
    }
  }
}

/**
 * Fetch persisted lux-door auto open/close config.
 */
export async function getLuxDoorConfig() {
  const response = await fetch(`${API_BASE_URL}/sensor/lux-door/config`)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP error! status: ${response.status}`)
  }
  return payload
}

/**
 * Update persisted lux-door config.
 * @param {{enabled?: boolean, luxThreshold?: number, luxTriggerOffset?: number}} patch
 */
export async function updateLuxDoorConfig(patch = {}) {
  const response = await fetch(`${API_BASE_URL}/sensor/lux-door/config`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(patch)
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP error! status: ${response.status}`)
  }
  return payload
}

/**
 * Calibrate closed-door lux baseline using the current live ambient reading.
 */
export async function calibrateLuxDoorThreshold() {
  const response = await fetch(`${API_BASE_URL}/sensor/lux-door/calibrate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload?.error || `HTTP error! status: ${response.status}`)
  }
  return payload
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
