// API functions for waste statistics
const API_BASE_URL = 'http://localhost:5000/api'

/**
 * Record the outcome of a food item
 * @param {string} itemId - The ID of the food item
 * @param {string} outcome - 'consumed' or 'wasted'
 * @returns {Promise<void>}
 */
export async function recordItemOutcome(itemId, outcome) {
  try {
    const response = await fetch(`${API_BASE_URL}/stats/outcome`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        item_id: itemId,
        outcome: outcome
      })
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
