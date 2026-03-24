// API functions for recipe suggestions
import { apiUrl } from './apiBase'

const API_BASE_URL = apiUrl('/api')

/**
 * Clear the recipe cache on the server
 * @returns {Promise<void>}
 */
export async function clearRecipeCache() {
  try {
    const response = await fetch(`${API_BASE_URL}/recipes/cache/clear`, {
      method: 'POST'
    })
    if (!response.ok) {
      throw new Error(`Failed to clear cache: ${response.status}`)
    }
  } catch (error) {
    console.error('Error clearing cache:', error)
    throw error
  }
}

/**
 * Search for recipes based on available ingredients
 * @param {Object} filters - Optional filters for the search
 * @param {string} filters.cuisine - Cuisine type (e.g., 'italian', 'mexican')
 * @param {string} filters.type - Meal type (e.g., 'main course', 'dessert')
 * @param {string} filters.diet - Diet type (e.g., 'vegetarian', 'vegan')
 * @returns {Promise<Array>} Array of recipe objects
 */
export async function searchRecipes(filters = {}) {
  try {
    // Build query parameters
    const params = new URLSearchParams()
    if (filters.cuisine) params.append('cuisine', filters.cuisine)
    if (filters.type) params.append('type', filters.type)
    if (filters.diet) params.append('diet', filters.diet)
    
    const queryString = params.toString()
    const url = `${API_BASE_URL}/recipes/search${queryString ? '?' + queryString : ''}`
    
    const response = await fetch(url)
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || `HTTP error! status: ${response.status}`)
    }
    
    const data = await response.json()
    
    // Handle response format: either direct array or {error, recipes} object
    if (data.error && data.recipes) {
      // API returned error but has cached results
      return { error: data.error, recipes: data.recipes }
    } else if (Array.isArray(data)) {
      // Normal response
      return { recipes: data }
    } else {
      // Unexpected format
      return { recipes: [] }
    }
  } catch (error) {
    console.error('Error fetching recipes:', error)
    throw error
  }
}
