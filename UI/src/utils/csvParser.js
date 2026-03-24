import { apiUrl } from './apiBase'

const API_URL = apiUrl('/api')

export async function loadFoodsFromCSV() {
  try {
    const response = await fetch(`${API_URL}/foods`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const foods = await response.json()
    return foods
  } catch (error) {
    console.error('Error loading foods from API:', error)
    return []
  }
}

export async function createFood(foodData) {
  try {
    const response = await fetch(`${API_URL}/foods`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(foodData)
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error creating food:', error)
    throw error
  }
}

export async function updateFood(id, foodData) {
  try {
    const response = await fetch(`${API_URL}/foods/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(foodData)
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error updating food:', error)
    throw error
  }
}

export async function deleteFood(id) {
  try {
    const response = await fetch(`${API_URL}/foods/${id}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('Error deleting food:', error)
    throw error
  }
}
