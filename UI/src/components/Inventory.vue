<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { loadFoodsFromCSV, createFood, updateFood, deleteFood } from '../utils/csvParser'
import { recordItemOutcome } from '../utils/statsApi'

defineProps({
  msg: String,
})

const count = ref(0)
const sortBy = ref(localStorage.getItem('inventorySortBy') || 'freshnessScore') // Restore from localStorage or default
const sortDirection = ref(localStorage.getItem('inventorySortDirection') || 'asc') // 'asc' or 'desc'
const filterBy = ref(localStorage.getItem('inventoryFilterBy') || 'all') // Restore from localStorage or default
const storageFilter = ref(localStorage.getItem('inventoryStorageFilter') || 'all') // 'all', 'regular', or 'humidity-controlled'
const controlsExpanded = ref(localStorage.getItem('inventoryControlsExpanded') === 'true') // Toggle for showing/hiding controls on narrow screens
const selectedCard = ref(null)
const showPopup = ref(false)
const showAddPopup = ref(false)
const isEditMode = ref(false)
const showDeleteConfirm = ref(false)
const cards = ref([])

// Edited food data
const editedFood = ref({
  name: '',
  foodGroup: '',
  packagingType: '',
  expirationDate: ''
})

// New food form data
const newFood = ref({
  name: '',
  foodGroup: 'other',
  daysInFridge: 0,
  packagingType: 'sealed',
  storageLocation: 'regular',
  expirationDate: ''
})

// Available food groups for filtering
const foodGroups = [
  { value: 'all', label: 'All Items' },
  { value: 'dairy', label: 'Dairy' },
  { value: 'produce', label: 'Produce' },
  { value: 'meat', label: 'Meat' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'condiment', label: 'Condiment' },
  { value: 'prepared', label: 'Prepared' },
  { value: 'other', label: 'Other' },
]

// Available storage locations for filtering
const storageLocations = [
  { value: 'all', label: 'All Storage' },
  { value: 'regular', label: 'Regular' },
  { value: 'humidity-controlled', label: 'Humidity-Controlled' },
]

// Function to parse time in fridge string to days
const parseTimeInFridge = (timeString) => {
  const match = timeString.match(/(\d+)\s*(hour|day)s?/i)
  if (!match) return 0
  
  const value = parseInt(match[1])
  const unit = match[2].toLowerCase()
  
  // Convert hours to days for proper comparison
  if (unit === 'hour') {
    return value / 24
  }
  return value
}

// Computed property for filtered and sorted cards
const sortedCards = computed(() => {
  let filteredCards = [...cards.value]
  
  // Apply food group filter
  if (filterBy.value !== 'all') {
    filteredCards = filteredCards.filter(card => card.foodGroup === filterBy.value)
  }
  
  // Apply storage location filter
  if (storageFilter.value !== 'all') {
    filteredCards = filteredCards.filter(card => card.storageLocation === storageFilter.value)
  }
  
  // Apply sorting
  return filteredCards.sort((a, b) => {
    let comparison = 0
    switch (sortBy.value) {
      case 'freshnessScore':
        comparison = a.freshnessScore - b.freshnessScore
        break
      case 'daysUntilSpoilage':
        comparison = a.daysUntilSpoilage - b.daysUntilSpoilage
        break
      case 'timeInFridge':
        comparison = parseTimeInFridge(a.timeInFridge) - parseTimeInFridge(b.timeInFridge)
        break
      default:
        comparison = 0
    }
    // Apply sort direction
    return sortDirection.value === 'desc' ? -comparison : comparison
  })
})

// Save sort and filter preferences to localStorage
watch(sortBy, (newValue) => {
  localStorage.setItem('inventorySortBy', newValue)
})

watch(filterBy, (newValue) => {
  localStorage.setItem('inventoryFilterBy', newValue)
})

watch(sortDirection, (newValue) => {
  localStorage.setItem('inventorySortDirection', newValue)
})

watch(storageFilter, (newValue) => {
  localStorage.setItem('inventoryStorageFilter', newValue)
})

watch(controlsExpanded, (newValue) => {
  localStorage.setItem('inventoryControlsExpanded', newValue.toString())
})

// Generate alerts for a specific food item
const getAlertsForFood = (food) => {
  if (!food) return []
  
  const alerts = []
  
  // If food has spoiled, only show spoiled alert
  if (food.freshnessScore <= 0) {
    alerts.push({
      type: 'critical',
      message: `${food.name} has likely spoiled! Check and discard immediately.`
    })
    return alerts
  }
  
  if (food.daysUntilSpoilage <= 1) {
    const message = food.daysUntilSpoilage === 0 
      ? `Will likely start to spoil in the next 24 hours!`
      : `Will spoil in ${food.daysUntilSpoilage} day${food.daysUntilSpoilage !== 1 ? 's' : ''}!`
    alerts.push({
      type: 'critical',
      message: message
    })
  } else if (food.daysUntilSpoilage === 2) {
    alerts.push({
      type: 'warning',
      message: `Will spoil in ${food.daysUntilSpoilage} days.`
    })
  }
  
  if (food.freshnessScore < 15) {
    alerts.push({
      type: 'warning',
      message: `Low freshness (${Math.round(food.freshnessScore)}/100).`
    })
  }
  
  return alerts
}

// Get alerts for selected card
const selectedCardAlerts = computed(() => {
  return selectedCard.value ? getAlertsForFood(selectedCard.value) : []
})

const handleCardClick = (cardId) => {
  selectedCard.value = cards.value.find(card => card.id === cardId)
  showPopup.value = true
}

const closePopup = () => {
  showPopup.value = false
  selectedCard.value = null
  isEditMode.value = false
}

const openAddPopup = () => {
  showAddPopup.value = true
}

const closeAddPopup = () => {
  showAddPopup.value = false
  // Reset form
  newFood.value = {
    name: '',
    foodGroup: 'other',
    daysInFridge: 0,
    packagingType: 'sealed',
    storageLocation: 'regular',
    expirationDate: ''
  }
}

const enableEditMode = () => {
  if (selectedCard.value) {
    editedFood.value = {
      name: selectedCard.value.name,
      foodGroup: selectedCard.value.foodGroup,
      packagingType: selectedCard.value.packagingType || 'sealed',
      storageLocation: selectedCard.value.storageLocation || 'regular',
      expirationDate: selectedCard.value.expirationDate || ''
    }
    isEditMode.value = true
  }
}

const cancelEdit = () => {
  isEditMode.value = false
  editedFood.value = {
    name: '',
    foodGroup: '',
    packagingType: '',
    storageLocation: '',
    expirationDate: ''
  }
}

const saveEdit = async () => {
  try {
    if (!editedFood.value.name.trim()) {
      alert('Please enter a food name')
      return
    }

    // Update the food item via API
    await updateFood(selectedCard.value.id, {
      name: editedFood.value.name,
      foodGroup: editedFood.value.foodGroup,
      packagingType: editedFood.value.packagingType,
      storageLocation: editedFood.value.storageLocation,
      expirationDate: editedFood.value.expirationDate
    })
    
    // Refresh the list
    const updatedFoods = await loadFoodsFromCSV()
    cards.value = updatedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    
    // Update selected card
    selectedCard.value = cards.value.find(card => card.id === selectedCard.value.id)
    
    isEditMode.value = false
  } catch (error) {
    console.error('Error updating food:', error)
    alert('Failed to update food item. Please try again.')
  }
}

const openDeleteConfirm = () => {
  showDeleteConfirm.value = true
}

const closeDeleteConfirm = () => {
  showDeleteConfirm.value = false
}

const deleteItemOutcome = ref('consumed') // Track why the item is being removed

const confirmDelete = async () => {
  try {
    if (!selectedCard.value) return
    
    // Record the outcome before deleting
    await recordItemOutcome(selectedCard.value.id, deleteItemOutcome.value)
    
    // Delete the food item via API
    await deleteFood(selectedCard.value.id)
    
    // Refresh the list
    const updatedFoods = await loadFoodsFromCSV()
    cards.value = updatedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    
    // Close both dialogs
    showDeleteConfirm.value = false
    showPopup.value = false
    selectedCard.value = null
    deleteItemOutcome.value = 'consumed' // Reset to default
  } catch (error) {
    console.error('Error deleting food:', error)
    alert('Failed to delete food item. Please try again.')
  }
}

const handleAddFood = async () => {
  try {
    if (!newFood.value.name.trim()) {
      alert('Please enter a food name')
      return
    }

    // Create the food item via API
    await createFood({
      name: newFood.value.name,
      foodGroup: newFood.value.foodGroup,
      packagingType: newFood.value.packagingType,
      storageLocation: newFood.value.storageLocation,
      expirationDate: newFood.value.expirationDate,
      daysInFridge: newFood.value.daysInFridge,
      freshnessScore: 100,
      daysUntilSpoilage: 7
    })
    
    // Refresh the list
    const updatedFoods = await loadFoodsFromCSV()
    cards.value = updatedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    
    closeAddPopup()
  } catch (error) {
    console.error('Error adding food:', error)
    alert('Failed to add food item. Please try again.')
  }
}

const handleKeyDown = (event) => {
  if (event.key === 'Escape') {
    if (showDeleteConfirm.value) {
      closeDeleteConfirm()
    } else if (isEditMode.value) {
      cancelEdit()
    } else {
      showPopup.value = false
      showAddPopup.value = false
    }
  }
}

let cardsUpdateInterval

onMounted(async () => {
  const foods = await loadFoodsFromCSV()
  // Transform foods to cards format with title property
  cards.value = foods.map(food => ({
    ...food,
    title: food.name
  }))
  window.addEventListener('keydown', handleKeyDown)
  
  // Poll for food data updates every 3 seconds
  cardsUpdateInterval = setInterval(async () => {
    const updatedFoods = await loadFoodsFromCSV()
    const updatedCards = updatedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    // Only update if data actually changed
    if (JSON.stringify(updatedCards) !== JSON.stringify(cards.value)) {
      cards.value = updatedCards
    }
  }, 3000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  clearInterval(cardsUpdateInterval)
})

const getFreshnessColor = (score) => {
  if (score <= 15) return '#8B0000' // Dark red
  if (score > 15 && score <= 39) return '#FF6B6B' // Light red
  if (score > 39 && score <= 59) return '#FFD700' // Yellow
  if (score > 59 && score <= 84) return '#ADFF2F' // Yellow-green (lighter and more yellow)
  if (score > 84) return '#228B22' // Forest green (lighter than dark green)
  return '#D3D3D3' // Default gray
}
</script>

<template>
  <div>
    <div class="controls-header">
      <button class="toggle-controls-button" @click="controlsExpanded = !controlsExpanded">
        {{ controlsExpanded ? '▼ Hide Filters' : '▶ Show Filters' }}
      </button>
      <button class="new-item-button mobile-new-item" @click="openAddPopup">+ New Item</button>
    </div>

    <div v-show="controlsExpanded" class="controls-container">
      <div class="filter-controls">
        <h2>Category:</h2>
        <select v-model="filterBy">
          <option v-for="group in foodGroups" :key="group.value" :value="group.value">
            {{ group.label }}
          </option>
        </select>
      </div>

      <div class="filter-controls">
        <h2>Storage:</h2>
        <select v-model="storageFilter">
          <option v-for="location in storageLocations" :key="location.value" :value="location.value">
            {{ location.label }}
          </option>
        </select>
      </div>

      <div class="sort-controls">
        <h2>Sort by:</h2>
        <button 
          :class="{ active: sortBy === 'freshnessScore' }"
          @click="sortBy = 'freshnessScore'"
        >
          Freshness Score
        </button>
        <button 
          :class="{ active: sortBy === 'daysUntilSpoilage' }"
          @click="sortBy = 'daysUntilSpoilage'"
        >
          Days Until Spoilage
        </button>
        <button 
          :class="{ active: sortBy === 'timeInFridge' }"
          @click="sortBy = 'timeInFridge'"
        >
          Time in Fridge
        </button>
        <button 
          class="sort-direction-toggle"
          @click="sortDirection = sortDirection === 'asc' ? 'desc' : 'asc'"
          :title="sortDirection === 'asc' ? 'Low to High' : 'High to Low'"
        >
          {{ sortDirection === 'asc' ? '↑' : '↓' }}
        </button>
      </div>

      <button class="new-item-button desktop-new-item" @click="openAddPopup">+ New Item</button>
    </div>

    <!-- Empty State Message -->
    <div v-if="sortedCards.length === 0" class="empty-state">
      <p>No items to display</p>
    </div>

    <!-- Cards Grid -->
    <div v-else class="cards-grid">
      <div 
        v-for="card in sortedCards" 
        :key="card.id"
        class="card-item"
        :style="{ borderColor: getFreshnessColor(card.freshnessScore) }"
        @click="handleCardClick(card.id)"
      >
        <div class="card-header">
          <h3>{{ card.title }}</h3>
          <span class="freshness-score" :style="{ color: getFreshnessColor(card.freshnessScore) }">{{ Math.round(card.freshnessScore) }}</span>
        </div>
        <p>Estimated days until spoilage: {{ card.daysUntilSpoilage }}</p>
        <p>Time in fridge: {{ card.timeInFridge }}</p>
      </div>
    </div>

    <!-- Food Details Popup -->
    <div v-if="showPopup" class="popup-overlay" @click="closePopup">
      <div class="popup-content" @click.stop>
        <div class="popup-header">
          <div class="header-title-section">
            <h2 v-if="!isEditMode">{{ selectedCard?.title }}</h2>
            <input 
              v-else
              v-model="editedFood.name"
              type="text"
              class="edit-title-input"
              placeholder="Food name"
            />
            <button v-if="!isEditMode" class="edit-button" @click="enableEditMode" title="Edit food item">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
              </svg>
            </button>
          </div>
          <button class="close-button" @click="closePopup">&times;</button>
        </div>
        <div class="popup-body" v-if="selectedCard">
          <div class="detail-item">
            <span class="detail-label">Freshness Score:</span>
            <span class="detail-value" :style="{ color: getFreshnessColor(selectedCard.freshnessScore) }">
              {{ Math.round(selectedCard.freshnessScore) }}/100
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Food Group:</span>
            <span v-if="!isEditMode" class="detail-value">{{ selectedCard.foodGroup.charAt(0).toUpperCase() + selectedCard.foodGroup.slice(1) }}</span>
            <select v-else v-model="editedFood.foodGroup" class="edit-select">
              <option value="dairy">Dairy</option>
              <option value="produce">Produce</option>
              <option value="meat">Meat</option>
              <option value="beverage">Beverage</option>
              <option value="condiment">Condiment</option>
              <option value="prepared">Prepared/Leftovers</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div class="detail-item">
            <span class="detail-label">Packaging Type:</span>
            <span v-if="!isEditMode" class="detail-value">{{ selectedCard.packagingType ? selectedCard.packagingType.charAt(0).toUpperCase() + selectedCard.packagingType.slice(1) : 'Unknown' }}</span>
            <select v-else v-model="editedFood.packagingType" class="edit-select">
              <option value="sealed">Sealed</option>
              <option value="air-tight container">Air-tight Container</option>
              <option value="opened">Opened</option>
              <option value="loose">Loose</option>
              <option value="carton">Carton</option>
              <option value="bottle">Bottle</option>
              <option value="jar">Jar</option>
            </select>
          </div>
          <div class="detail-item">
            <span class="detail-label">Storage:</span>
            <span v-if="!isEditMode" class="detail-value">{{ selectedCard.storageLocation === 'humidity-controlled' ? 'Humidity-Controlled' : 'Regular' }}</span>
            <select v-else v-model="editedFood.storageLocation" class="edit-select">
              <option value="regular">Regular</option>
              <option value="humidity-controlled">Humidity-Controlled</option>
            </select>
          </div>
          <div class="detail-item">
            <span class="detail-label">Time in Fridge:</span>
            <span class="detail-value">{{ selectedCard.timeInFridge }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Days Until Spoilage:</span>
            <span class="detail-value">{{ selectedCard.daysUntilSpoilage }} days</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Status:</span>
            <span class="detail-value" :style="{ color: getFreshnessColor(selectedCard.freshnessScore) }">
              {{ selectedCard.freshnessScore <= 15 ? 'Poor' : selectedCard.freshnessScore <= 39 ? 'Fair' : selectedCard.freshnessScore <= 59 ? 'Good' : selectedCard.freshnessScore <= 84 ? 'Very Good' : 'Excellent' }}
            </span>
          </div>
          <div v-if="selectedCard.expirationDate || isEditMode" class="detail-item">
            <span class="detail-label">Expiration Date:</span>
            <span v-if="!isEditMode" class="detail-value">{{ new Date(selectedCard.expirationDate).toLocaleDateString() }}</span>
            <input 
              v-else
              v-model="editedFood.expirationDate"
              type="date"
              class="edit-date-input"
            />
          </div>
          
          <!-- Edit Mode Actions -->
          <div v-if="isEditMode" class="edit-actions">
            <button type="button" class="cancel-edit-button" @click="cancelEdit">Cancel</button>
            <button type="button" class="save-edit-button" @click="saveEdit">Save Changes</button>
          </div>
          
          <!-- Delete Button -->
          <div v-if="!isEditMode" class="delete-section">
            <button type="button" class="delete-button" @click="openDeleteConfirm">Remove From Inventory</button>
          </div>
          
          <!-- Alerts Section -->
          <div v-if="selectedCardAlerts.length > 0" class="alerts-section">
            <h3 class="alerts-title">Alerts</h3>
            <div 
              v-for="(alert, index) in selectedCardAlerts" 
              :key="index"
              class="alert-item"
              :class="alert.type"
            >
              <span class="alert-icon">{{ alert.type === 'critical' ? '⚠️' : '⚡' }}</span>
              <span class="alert-message">{{ alert.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add New Item Popup -->
    <div v-if="showAddPopup" class="popup-overlay" @click="closeAddPopup">
      <div class="popup-content" @click.stop>
        <div class="popup-header">
          <h2>Add New Food Item</h2>
          <button class="close-button" @click="closeAddPopup">&times;</button>
        </div>
        <div class="popup-body">
          <form @submit.prevent="handleAddFood" class="add-food-form">
            <div class="form-group">
              <label for="foodName">Item Name *</label>
              <input 
                id="foodName"
                v-model="newFood.name" 
                type="text" 
                placeholder="e.g., Milk, Broccoli, Eggs"
                required
              />
            </div>
            
            <div class="form-group">
              <label for="foodGroup">Food Group *</label>
              <select id="foodGroup" v-model="newFood.foodGroup">
                <option value="dairy">Dairy</option>
                <option value="produce">Produce</option>
                <option value="meat">Meat</option>
                <option value="beverage">Beverage</option>
                <option value="condiment">Condiment</option>
                <option value="prepared">Prepared/Leftovers</option>
                <option value="other">Other</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="daysInFridge">Days in Fridge</label>
              <input 
                id="daysInFridge"
                v-model.number="newFood.daysInFridge" 
                type="number" 
                min="0"
              />
            </div>
            
            <div class="form-group">
              <label for="packagingType">Packaging Type</label>
              <select id="packagingType" v-model="newFood.packagingType">
                <option value="sealed">Sealed</option>
                <option value="air-tight container">Air-tight Container</option>
                <option value="opened">Opened</option>
                <option value="loose">Loose</option>
                <option value="carton">Carton</option>
                <option value="bottle">Bottle</option>
                <option value="jar">Jar</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="storageLocation">Storage</label>
              <select id="storageLocation" v-model="newFood.storageLocation">
                <option value="regular">Regular</option>
                <option value="humidity-controlled">Humidity-Controlled</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="expirationDate">Expiration Date (Optional)</label>
              <input 
                id="expirationDate"
                v-model="newFood.expirationDate" 
                type="date"
              />
            </div>
            
            <div class="form-actions">
              <button type="button" class="cancel-button" @click="closeAddPopup">Cancel</button>
              <button type="submit" class="submit-button">Add Item</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Dialog -->
    <div v-if="showDeleteConfirm" class="popup-overlay" @click="closeDeleteConfirm">
      <div class="confirm-dialog" @click.stop>
        <div class="confirm-header">
          <h3>Remove From Inventory</h3>
        </div>
        <div class="confirm-body">
          <p>What happened to this item?</p>
          <p class="item-name">{{ selectedCard?.name }}</p>
          
          <div class="outcome-options">
            <label class="outcome-option">
              <input type="radio" v-model="deleteItemOutcome" value="consumed" />
              <span class="outcome-label">
                <span class="outcome-icon">✅</span>
                <span>Consumed</span>
              </span>
            </label>
            <label class="outcome-option">
              <input type="radio" v-model="deleteItemOutcome" value="wasted" />
              <span class="outcome-label">
                <span class="outcome-icon">❌</span>
                <span>Wasted/Spoiled</span>
              </span>
            </label>
          </div>
        </div>
        <div class="confirm-actions">
          <button type="button" class="confirm-cancel-button" @click="closeDeleteConfirm">Cancel</button>
          <button type="button" class="confirm-delete-button" @click="confirmDelete">Confirm</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  margin-top: 2rem;
}

.empty-state p {
  font-size: 1.5rem;
  color: oklch(0.6 0 0);
  font-weight: 500;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(20px, 300px));
  gap: 1.5rem;
  margin-top: 1rem;
  width: 100%;
  padding: 0 1rem 2rem 1rem;
}

.card-item {
  background-color: oklch(0.25 0 0);
  border: 1px solid;
  border-radius: 8px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
  min-width: 0;
  overflow: hidden;
}

.card-item:hover {
  background-color: oklch(0.3 0 0);
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  filter: brightness(1.1);
}

.card-item h3 {
  margin: 0 0 0.5rem 0;
  font-size: clamp(1rem, 2vw, 1.25rem);
  word-break: break-word;
  overflow-wrap: break-word;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}

.freshness-score {
  font-size: 1.1rem;
  font-weight: bold;
  flex-shrink: 0;
}

.card-item p {
  margin: 0;
  font-size: 0.875rem;
  word-break: break-word;
  overflow-wrap: break-word;
}

.controls-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0 1rem;
}

.toggle-controls-button {
  background-color: transparent;
  color: oklch(0.9 0 0);
  border: 1px solid oklch(0.4 0 0);
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.toggle-controls-button:hover {
  opacity: 0.8;
}

.controls-container {
  display: flex;
  flex-wrap: wrap;
  /* gap: 2rem; */
  align-items: center;
  margin-bottom: 1rem;
  padding: 0 1rem;
}

.new-item-button {
  background-color: oklch(0.6 0.2 265);
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  white-space: nowrap;
  margin-left: auto;
  /* margin-right: 2rem; */
}

.new-item-button:hover {
  background-color: oklch(0.65 0.22 265);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(139, 69, 19, 0.4);
}

.filter-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background-color: oklch(0.2 0 0);
  border-radius: 8px;
  /* border: 1px solid oklch(0.4 0 0); */
}

.sort-controls h2 {
  margin: 0;
  font-size: 1rem;
  color: oklch(0.9 0 0);
}

.sort-controls button {
  padding: 0.5rem 1rem;
  background-color: oklch(0.25 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  color: oklch(0.9 0 0);
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.3s ease;
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.sort-controls button:hover {
  background-color: oklch(0.3 0 0);
  border-color: oklch(0.55 0.15 265);
  transform: translateY(-1px);
}

.sort-controls button.active {
  background-color: oklch(0.35 0 0);
  border-color: oklch(0.6 0.2 265);
  color: oklch(1 0 0);
  font-weight: bold;
}

.sort-direction-toggle {
  min-width: 48px !important;
  padding: 0.5rem 1rem !important;
  font-size: 1rem !important;
  background-color: oklch(0.3 0 0) !important;
  border: 2px solid oklch(0.5 0 0) !important;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 38px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
}

.sort-direction-toggle:hover {
  background-color: oklch(0.35 0 0) !important;
  border-color: oklch(0.6 0 0) !important;
}

.sort-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background-color: oklch(0.2 0 0);
  border-radius: 8px;
  /* border: 1px solid oklch(0.4 0 0); */
}

.filter-controls h2 {
  margin: 0;
  font-size: 1rem;
  color: oklch(0.9 0 0);
}

.filter-controls select {
  padding: 0.5rem 1rem;
  background-color: oklch(0.25 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  color: oklch(0.9 0 0);
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.filter-controls select:hover {
  background-color: oklch(0.3 0 0);
  border-color: oklch(0.55 0.15 265);
}

.filter-controls select:focus {
  outline: none;
  border-color: oklch(0.6 0.2 265);
  box-shadow: 0 0 0 2px rgba(139, 69, 19, 0.2);
}

/* Popup Styles */
.popup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.popup-content {
  background-color: oklch(0.25 0 0);
  border: 2px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 0;
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid oklch(0.4 0 0);
}

.header-title-section {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
}

.popup-header h2 {
  margin: 0;
  color: oklch(0.9 0 0);
  font-size: 1.5rem;
  word-break: break-word;
  overflow-wrap: break-word;
}

.edit-title-input {
  padding: 0.5rem;
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  background-color: oklch(0.15 0 0);
  color: oklch(0.95 0 0);
  font-size: 1.5rem;
  font-weight: 600;
  flex: 1;
}

.edit-title-input:focus {
  outline: none;
  border-color: oklch(0.65 0.2 240);
  box-shadow: 0 0 0 3px rgba(100, 149, 237, 0.1);
}

.edit-button {
  background: none;
  border: none;
  color: oklch(0.7 0 0);
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.3s ease;
}

.edit-button:hover {
  background-color: oklch(0.3 0 0);
  color: oklch(0.9 0 0);
}

.edit-button svg {
  width: 18px;
  height: 18px;
}

.close-button {
  background: none;
  border: none;
  font-size: 2rem;
  color: oklch(0.7 0 0);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.close-button:hover {
  background-color: oklch(0.3 0 0);
  color: oklch(0.9 0 0);
}

.popup-body {
  padding: 1.5rem;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid oklch(0.15 0 0);
}

.detail-item:last-child {
  border-bottom: none;
}

.detail-label {
  font-weight: 600;
  color: oklch(0.8 0 0);
  font-size: 1rem;
}

.detail-value {
  font-weight: 500;
  color: oklch(0.9 0 0);
  font-size: 1rem;
}

/* Edit Mode Styles */
.edit-select {
  padding: 0.5rem;
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  background-color: oklch(0.15 0 0);
  color: oklch(0.95 0 0);
  font-size: 1rem;
  cursor: pointer;
  transition: border-color 0.2s;
}

.edit-select:focus {
  outline: none;
  border-color: oklch(0.65 0.2 240);
  box-shadow: 0 0 0 3px rgba(100, 149, 237, 0.1);
}

.edit-date-input {
  padding: 0.5rem;
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  background-color: oklch(0.15 0 0);
  color: oklch(0.95 0 0);
  font-size: 1rem;
  transition: border-color 0.2s;
}

.edit-date-input:focus {
  outline: none;
  border-color: oklch(0.65 0.2 240);
  box-shadow: 0 0 0 3px rgba(100, 149, 237, 0.1);
}

.edit-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 2px solid oklch(0.3 0 0);
}

.cancel-edit-button,
.save-edit-button {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-edit-button {
  background-color: oklch(0.3 0 0);
  color: oklch(0.85 0 0);
}

.cancel-edit-button:hover {
  background-color: oklch(0.35 0 0);
}

.save-edit-button {
  background-color: oklch(0.65 0.2 240);
  color: white;
}

.save-edit-button:hover {
  background-color: oklch(0.7 0.2 240);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(100, 149, 237, 0.3);
}

/* Delete Section */
.delete-section {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 2px solid oklch(0.3 0 0);
}

.delete-button {
  width: 100%;
  padding: 0.75rem;
  background-color: #8B0000;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.delete-button:hover {
  background-color: #A52A2A;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(139, 0, 0, 0.4);
}

/* Confirmation Dialog */
.confirm-dialog {
  background-color: oklch(0.25 0 0);
  border: 2px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 0;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.confirm-header {
  padding: 1.5rem;
  border-bottom: 1px solid oklch(0.4 0 0);
}

.confirm-header h3 {
  margin: 0;
  color: oklch(0.9 0 0);
  font-size: 1.25rem;
}

.confirm-body {
  padding: 1.5rem;
}

.confirm-body p {
  margin: 0 0 1rem 0;
  color: oklch(0.85 0 0);
  font-size: 1rem;
  line-height: 1.5;
}

.confirm-body .item-name {
  font-weight: 600;
  color: oklch(0.95 0 0);
  text-align: center;
  font-size: 1.1rem;
  margin: 0 0 1.5rem 0;
}

.outcome-options {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.outcome-option {
  display: flex;
  align-items: center;
  padding: 0.75rem;
  border: 2px solid oklch(0.4 0 0);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.outcome-option:hover {
  background-color: oklch(0.25 0 0);
  border-color: oklch(0.55 0.15 265);
}

.outcome-option input[type="radio"] {
  margin-right: 0.75rem;
  width: 18px;
  height: 18px;
  cursor: pointer;
}

.outcome-option input[type="radio"]:checked + .outcome-label {
  color: oklch(0.95 0 0);
  font-weight: 600;
}

.outcome-option input[type="radio"]:checked {
  accent-color: oklch(0.6 0.2 265);
}

.outcome-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: oklch(0.8 0 0);
  flex: 1;
}

.outcome-icon {
  font-size: 1.25rem;
}

.confirm-actions {
  display: flex;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid oklch(0.4 0 0);
}

.confirm-cancel-button,
.confirm-delete-button {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.confirm-cancel-button {
  background-color: oklch(0.3 0 0);
  color: oklch(0.85 0 0);
}

.confirm-cancel-button:hover {
  background-color: oklch(0.35 0 0);
}

.confirm-delete-button {
  background-color: #8B0000;
  color: white;
}

.confirm-delete-button:hover {
  background-color: #A52A2A;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(139, 0, 0, 0.4);
}

/* Alerts Section */
.alerts-section {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 2px solid oklch(0.3 0 0);
}

.alerts-title {
  margin: 0 0 1rem 0;
  color: oklch(0.85 0 0);
  font-size: 1.1rem;
  font-weight: 600;
}

.alert-item {
  display: flex;
  align-items: center;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  border-radius: 6px;
  border-left: 4px solid;
  background-color: oklch(0.2 0 0);
}

.alert-item.critical {
  border-left-color: #FF6B6B;
  background-color: rgba(255, 107, 107, 0.1);
}

.alert-item.warning {
  border-left-color: #FFD700;
  background-color: rgba(255, 215, 0, 0.1);
}

.alert-icon {
  font-size: 1.2rem;
  margin-right: 0.75rem;
}

.alert-message {
  color: oklch(0.9 0 0);
  font-size: 0.95rem;
}

/* Add Item Form Styles */
.add-food-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 0.5rem 0;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  color: oklch(0.9 0 0);
  font-size: 0.95rem;
  font-weight: 500;
}

.form-group input,
.form-group select {
  padding: 0.625rem;
  border: 1px solid oklch(0.3 0 0);
  border-radius: 6px;
  background-color: oklch(0.15 0 0);
  color: oklch(0.95 0 0);
  font-size: 1rem;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: oklch(0.65 0.2 240);
  box-shadow: 0 0 0 3px rgba(100, 149, 237, 0.1);
}

.form-group input[type="number"] {
  -moz-appearance: textfield;
}

.form-group input[type="number"]::-webkit-outer-spin-button,
.form-group input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.form-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.form-actions button {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.form-actions button[type="submit"] {
  background-color: oklch(0.65 0.2 240);
  color: white;
}

.form-actions button[type="submit"]:hover {
  background-color: oklch(0.7 0.2 240);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(100, 149, 237, 0.3);
}

.form-actions button[type="button"] {
  background-color: oklch(0.3 0 0);
  color: oklch(0.85 0 0);
}

.form-actions button[type="button"]:hover {
  background-color: oklch(0.35 0 0);
}

/* Wide screens - hide toggle button and always show controls */
@media (min-width: 1770px) {
  .toggle-controls-button,
  .mobile-new-item {
    display: none;
  }

  .controls-header {
    display: none;
  }

  .controls-container {
    display: flex !important;
    flex-wrap: wrap;
    /* gap: 2rem; */
    align-items: center;
    margin-bottom: 1rem;
    padding: 0 1rem;
  }

  .sort-controls h2 {
    width: auto;
    flex-basis: auto;
  }

  .desktop-new-item {
    margin-left: auto;
  }
}

/* Narrow screens - hide desktop button, show mobile button */
@media (max-width: 1769px) {
  .desktop-new-item {
    display: none;
  }
}

/* Responsive Design - Tablet */
@media (max-width: 1024px) {
  .cards-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;
  }

  .controls-container {
    flex-wrap: wrap;
    /* gap: 1rem; */
  }

  .new-item-button {
    margin-left: 0;
    margin-right: 0;
  }
}

/* Responsive Design - Mobile */
@media (max-width: 768px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }

  .controls-container {
    flex-direction: column;
    align-items: stretch;
    /* gap: 0.75rem; */
  }

  .filter-controls,
  .sort-controls {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
    gap: 0.5rem;
  }

  .filter-controls h2,
  .sort-controls h2 {
    width: 100%;
  }

  .sort-controls {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .sort-controls button {
    flex: 1 1 calc(50% - 0.5rem);
    min-width: 120px;
  }

  .sort-direction-toggle {
    flex: 0 0 auto !important;
    min-width: 50px !important;
  }

  .controls-header {
    flex-direction: row;
    gap: 0.75rem;
  }

  .toggle-controls-button,
  .mobile-new-item {
    flex: 1;
  }

  .card-item {
    padding: 1rem;
  }

  .popup-content {
    width: 95%;
    max-height: 90vh;
  }

  .popup-header {
    padding: 1rem;
  }

  .detail-section {
    padding: 1rem;
  }

  .edit-select,
  .edit-input {
    font-size: 16px; /* Prevents iOS zoom on focus */
  }
}

/* Responsive Design - Small Mobile */
@media (max-width: 480px) {
  .cards-grid {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  .card-item h3 {
    font-size: 1rem;
  }

  .freshness-score {
    font-size: 1rem;
  }

  .sort-controls button {
    flex: 1 1 100%;
    min-width: unset;
  }

  .filter-controls h2,
  .sort-controls h2 {
    font-size: 0.9rem;
  }

  .filter-controls select {
    font-size: 0.9rem;
    padding: 0.4rem 0.8rem;
  }

  .sort-controls button {
    font-size: 0.85rem;
    padding: 0.4rem 0.8rem;
  }
}

/* Improve touch targets for mobile */
@media (hover: none) and (pointer: coarse) {
  .card-item,
  button,
  select {
    min-height: 44px; /* Apple's recommended touch target size */
  }

  .sort-controls button {
    padding: 0.75rem 1rem;
  }

  .close-button {
    min-width: 44px;
    min-height: 44px;
  }
}
</style>
