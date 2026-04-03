// API functions for waste statistics
import { apiUrl } from './apiBase'

const API_BASE_URL = apiUrl('/api')

/**
 * Record the outcome of a food item
 * @param {string} itemId - The ID of the food item
 * @param {string} [outcome] - Optional explicit outcome ('consumed' or 'wasted')
 * @returns {Promise<void>}
 */
export async function recordItemOutcome(itemId, outcome) {
  try {
    const payload = { item_id: itemId }
    if (outcome) payload.outcome = outcome

    const response = await fetch(`${API_BASE_URL}/stats/outcome`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    
    return await response.json()
  } catch (error) {
    console.error('Error recording outcome:', error)
    throw error
  }
}

/**
 * Get historical waste statistics
 * @returns {Promise<Array>} Array of daily statistics
 */
export async function getWasteHistory() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats/history`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error fetching waste history:', error)
    return []
  }
}

/**
 * Get temperature history
 * @param {{scope?: 'recent'|'long', limit?: number}} [options]
 * @returns {Promise<Array>} Array of temperature readings with timestamps
 */
export async function getTemperatureHistory(options = {}) {
  try {
    const params = new URLSearchParams()
    if (options.scope) params.set('scope', options.scope)
    if (Number.isFinite(options.limit)) params.set('limit', String(Math.max(1, Math.floor(options.limit))))
    const query = params.toString()
    const response = await fetch(`${API_BASE_URL}/stats/temperature${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error fetching temperature history:', error)
    return []
  }
}

/**
 * Get MQ gas sensor history
 * @param {{scope?: 'recent'|'long', limit?: number}} [options]
 * @returns {Promise<Array>} Array of MQ sensor readings with timestamps
 */
export async function getMqHistory(options = {}) {
  try {
    const params = new URLSearchParams()
    if (options.scope) params.set('scope', options.scope)
    if (Number.isFinite(options.limit)) params.set('limit', String(Math.max(1, Math.floor(options.limit))))
    const query = params.toString()
    const response = await fetch(`${API_BASE_URL}/stats/mq${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error fetching MQ history:', error)
    return []
  }
}

/**
 * Get dominant gas severity and top suspected contributors
 * @returns {Promise<Object>} Gas contributor summary payload
 */
export async function getGasContributors() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats/gas-contributors`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error fetching gas contributors:', error)
    return {
      connected: false,
      severity: 'low',
      message: 'No abnormal gases detected.',
      details: '',
      dominantSensors: [],
      contributors: []
    }
  }
}
