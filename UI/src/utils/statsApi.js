// API functions for waste statistics
const API_BASE_URL = `${(import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:5000`).replace(/\/$/, '')}/api`

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
 * Get temperature history for the last 12 hours
 * @returns {Promise<Array>} Array of temperature readings with timestamps
 */
export async function getTemperatureHistory() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats/temperature`)
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
 * Get MQ gas sensor history for the last 12 hours
 * @returns {Promise<Array>} Array of MQ sensor readings with timestamps
 */
export async function getMqHistory() {
  try {
    const response = await fetch(`${API_BASE_URL}/stats/mq`)
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
