<script setup>
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated, watch } from 'vue'
import { loadFoodsFromCSV, createFood, updateFood, deleteFood } from '../utils/csvParser'

defineOptions({ name: 'Inventory' })
import { recordItemOutcome } from '../utils/statsApi'

const props = defineProps({
  msg: String,
  pendingItems: {
    type: Array,
    default: () => []
  },
  outgoingItems: {
    type: Array,
    default: () => []
  },
  disambiguationItems: {
    type: Array,
    default: () => []
  },
  claimedByOthers: {
    // Map of { [disambiguationId]: { confirmedIds: Set, removedIds: Set } }
    // Computed in App.vue and passed down so sibling-claimed options can be
    // visually disabled without altering the underlying data.
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['viewPendingItem', 'switchToIncoming', 'markAsNew', 'resolveDisambiguation', 'okDisambiguation'])

const count = ref(0)
const sortBy = ref(localStorage.getItem('inventorySortBy') || 'freshnessScore') // Restore from localStorage or default
const sortDirection = ref(localStorage.getItem('inventorySortDirection') || 'asc') // 'asc' or 'desc'
const filterBy = ref(localStorage.getItem('inventoryFilterBy') || 'all') // Restore from localStorage or default
const storageFilter = ref(localStorage.getItem('inventoryStorageFilter') || 'all') // 'all', 'regular', or 'humidity-controlled'
const controlsExpanded = ref(localStorage.getItem('inventoryControlsExpanded') === 'true') // Toggle for showing/hiding controls on narrow screens
const selectedCard = ref(null)
const showPopup = ref(false)
const showAddPopup = ref(false)
const showSpoilageBreakdown = ref(false)
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
  timeInFridgeHours: 0,
  timeOutsideFridgeHours: 0,
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
  { value: 'seafood', label: 'Seafood' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'condiment', label: 'Condiment' },
  { value: 'prepared', label: 'Prepared' },
  { value: 'other', label: 'Other' },
]

// Available storage locations for filtering
const storageLocations = [
  { value: 'all', label: 'All Storage' },
  { value: 'regular', label: 'Regular Shelf' },
  { value: 'crisper', label: 'Crisper Drawer' },
  { value: 'door', label: 'Door Shelf' },
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

// Computed property for pending items formatted as cards
const pendingCards = computed(() => {
  return props.pendingItems.map(item => {
    const now = new Date()
    const timeInFridge = item.time_in_fridge || '0 days'
    
    // Use stored spoilage prediction if available, otherwise calculate from expiration date
    let daysUntilSpoilage = item.days_until_spoilage ?? 7
    if (!item.days_until_spoilage && item.expiration_date) {
      const expirationDate = new Date(item.expiration_date)
      const diffDays = Math.ceil((expirationDate - now) / (1000 * 60 * 60 * 24))
      daysUntilSpoilage = diffDays > 0 ? diffDays : 0
    }
    
    return {
      id: `pending-${item.id}`,
      realId: item.id,
      title: item.predicted_class,
      name: item.predicted_class,
      foodGroup: item.category || 'other',
      packagingType: item.packaging_type || 'sealed',
      storageLocation: item.storage_location || 'regular',
      expirationDate: item.expiration_date || '',
      confidence: item.confidence,
      isPending: true,
      isReentry: !!item.isReentry,
      freshnessScore: item.isReentry ? (item.freshness_score ?? 100) : 100,
      daysUntilSpoilage: daysUntilSpoilage,
      timeInFridge: timeInFridge,
      entryDate: item.entry_date || '',
      description: item.description || '',
      safetyCategory: item.safety_category || '',
      warnings: item.warnings || [],
      cumulativeTempAbuse: item.cumulative_temp_abuse ?? 0,
      environmentAlerts: item.environment_alerts || []
    }
  })
})

// Computed property for outgoing items formatted as cards
const outgoingCards = computed(() => {
  return props.outgoingItems.map(item => ({
    id: `outgoing-${item.id}`,
    realId: item.id,
    title: item.name,
    name: item.name,
    foodGroup: item.foodGroup || 'other',
    packagingType: item.packagingType || 'sealed',
    storageLocation: item.storageLocation || 'regular',
    expirationDate: item.expirationDate || '',
    isOutgoing: true,
    freshnessScore: item.freshnessScore ?? 100,
    daysUntilSpoilage: item.daysUntilSpoilage ?? 7,
    timeInFridge: item.timeInFridge || '0 days',
    entryDate: item.entryDate || '',
    description: item.description || '',
    safetyCategory: item.safetyCategory || '',
    warnings: item.warnings || [],
    cumulativeTempAbuse: item.cumulativeTempAbuse ?? 0,
    environmentAlerts: item.environmentAlerts || []
  }))
})

// Computed property for disambiguation items formatted as cards
const disambiguationCards = computed(() => {
  return props.disambiguationItems.map(item => {
    const claimed = props.claimedByOthers[item.id] || { confirmedIds: new Set(), removedIds: new Set() }
    return {
      id: item.id,
      isDisambiguation: true,
      disambiguationType: item.type,
      confirmedMatches: item.confirmedMatches || [],
      removedMatches: item.removedMatches || [],
      defaultOutgoingId: item.defaultOutgoingId || null,
      defaultReentryId: item.defaultReentryId || null,
      selectedAction: item.selectedAction || null,
      selectedTargetId: item.selectedTargetId || null,
      // IDs already selected by a sibling card — buttons should be disabled
      siblingClaimedConfirmedIds: claimed.confirmedIds,
      siblingClaimedRemovedIds: claimed.removedIds
    }
  })
})

// Computed property for filtered and sorted cards (including pending)
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
  const sorted = filteredCards.sort((a, b) => {
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
  
  // Add disambiguation cards first, then outgoing, then pending, then sorted confirmed
  return [...disambiguationCards.value, ...outgoingCards.value, ...pendingCards.value, ...sorted]
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

  // Cumulative time outside the fridge at unsafe temperatures
  if (food.cumulativeTempAbuse > 0) {
    const h = food.cumulativeTempAbuse
    const label = h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`
    const alertType = h >= 4 ? 'critical' : 'warning'
    alerts.push({
      type: alertType,
      message: `Spent ${label} at unsafe temperatures (outside fridge or during transport).`
    })
  }

  // In-fridge environment alerts (unsafe fridge temperature / humidity events)
  if (food.environmentAlerts && food.environmentAlerts.length > 0) {
    // Group by type and sum durations so we don't show 20 individual rows
    const grouped = {}
    for (const ea of food.environmentAlerts) {
      if (!grouped[ea.alert_type]) grouped[ea.alert_type] = { total: 0, count: 0, latest: ea.detected_at }
      grouped[ea.alert_type].total += ea.duration_hours
      grouped[ea.alert_type].count += 1
      if (ea.detected_at > grouped[ea.alert_type].latest) grouped[ea.alert_type].latest = ea.detected_at
    }
    for (const [type, info] of Object.entries(grouped)) {
      const h = info.total
      const label = h < 1 ? `${Math.round(h * 60)} min` : `${h.toFixed(1)} h`
      const typeLabel = type === 'temperature' ? 'unsafe fridge temperature'
                      : type === 'humidity'    ? 'unsafe fridge humidity'
                      : 'unsafe fridge temperature and humidity'
      const alertLevel = h >= 1 ? 'critical' : 'warning'
      alerts.push({
        type: alertLevel,
        message: `Fridge conditions were unsafe (${typeLabel}) for ${label} while this item was stored.`
      })
    }
  }

  return alerts
}

// Get alerts for selected card
const selectedCardAlerts = computed(() => {
  return selectedCard.value ? getAlertsForFood(selectedCard.value) : []
})

const handleCardClick = (cardId) => {
  // Check if it's a pending item
  if (cardId.startsWith('pending-')) {
    const pendingCard = pendingCards.value.find(c => c.id === cardId)
    // Re-entry cards show the details popup (read-only)
    if (pendingCard && pendingCard.isReentry) {
      selectedCard.value = pendingCard
      showPopup.value = true
      return
    }
    // Regular pending cards show the scan-confirmation popup
    const pendingItem = props.pendingItems.find(item => `pending-${item.id}` === cardId)
    if (pendingItem) {
      emit('viewPendingItem', pendingItem)
      return
    }
  }

  // Outgoing cards show the details popup (read-only)
  if (cardId.startsWith('outgoing-')) {
    const outgoingCard = outgoingCards.value.find(c => c.id === cardId)
    if (outgoingCard) {
      selectedCard.value = outgoingCard
      showPopup.value = true
    }
    return
  }

  // Skip disambiguation cards — buttons inside handle all actions
  if (cardId.startsWith('disambiguation-')) {
    return
  }

  // Regular card click
  selectedCard.value = cards.value.find(card => card.id === cardId)
  showPopup.value = true
}

const handleSubCardClick = (subItem, isRemoved) => {
  selectedCard.value = {
    id: subItem.id,
    title: subItem.name,
    name: subItem.name,
    foodGroup: subItem.foodGroup || 'other',
    packagingType: subItem.packagingType || '',
    storageLocation: subItem.storageLocation || 'regular',
    expirationDate: subItem.expirationDate || '',
    freshnessScore: subItem.freshnessScore ?? 100,
    daysUntilSpoilage: subItem.daysUntilSpoilage ?? 7,
    timeInFridge: isRemoved ? `removed ${subItem.hoursOutside ?? 0}h ago` : (subItem.timeInFridge ?? ''),
    entryDate: subItem.entryDate || '',
    description: subItem.description || '',
    cumulativeTempAbuse: subItem.cumulativeTempAbuse ?? 0,
    environmentAlerts: subItem.environmentAlerts || [],
    warnings: subItem.warnings || [],
    safetyCategory: subItem.safetyCategory || '',
    // Mark read-only so the popup hides edit/delete controls
    isOutgoing: true
  }
  showPopup.value = true
}

const closePopup = () => {
  showPopup.value = false
  selectedCard.value = null
  isEditMode.value = false
  showSpoilageBreakdown.value = false
}

const factorClass = (v) => {
  if (v === undefined || v === null) return ''
  if (v >= 0.95) return 'factor-good'
  if (v >= 0.7) return 'factor-warn'
  return 'factor-bad'
}

const tempFactorStatus = (v) => {
  if (v === undefined || v === null) return ''
  if (v >= 1.0) return '✓ Optimal or cooler'
  if (v >= 0.95) return '✓ Safe range'
  if (v >= 0.75) return '⚠ Elevated – accelerating spoilage'
  return '⚠ High – significant spoilage acceleration'
}

const abuseSummary = (cumulativeHours, tempFactor) => {
  if (!cumulativeHours || cumulativeHours <= 0) return 'No exposure recorded'
  const hStr = cumulativeHours < 1
    ? `${Math.round(cumulativeHours * 60)} min`
    : `${cumulativeHours.toFixed(1)}h`
  if (tempFactor !== undefined && tempFactor < 0.95)
    return `${hStr} total — currently ongoing`
  return `${hStr} total — temperature normalized`
}

const gasFactorStatus = (metadata) => {
  if (!metadata || metadata.gas_factor === undefined || metadata.gas_factor === null) return ''
  if (metadata.gas_status === 'high') return '⚠ High gas detected'
  if (metadata.gas_status === 'elevated') return '⚠ Elevated gas detected'
  if (metadata.gas_status === 'low') return '✓ Gas levels normal'
  return ''
}

const formatAbuseHours = (hours) => {
  if (!hours || hours <= 0) return ''
  if (hours < 1) return `${Math.round(hours * 60)}m`
  return `${hours.toFixed(1)}h`
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
    timeInFridgeHours: 0,
    timeOutsideFridgeHours: 0,
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
    const confirmedFoods = updatedFoods.filter(food => food.status === 'confirmed')
    cards.value = confirmedFoods.map(food => ({
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

const confirmDelete = async () => {
  try {
    if (!selectedCard.value) return
    
    // Record inferred outcome before deleting (backend infers from freshness).
    await recordItemOutcome(selectedCard.value.id)
    
    // Delete the food item via API
    await deleteFood(selectedCard.value.id)
    
    // Refresh the list
    const updatedFoods = await loadFoodsFromCSV()
    const confirmedFoods = updatedFoods.filter(food => food.status === 'confirmed')
    cards.value = confirmedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    
    // Close both dialogs
    showDeleteConfirm.value = false
    showPopup.value = false
    selectedCard.value = null
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

    // Capitalize food name for consistency
    const capitalizeName = (name) => {
      return name.split(' ').map(word => 
        word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
      ).join(' ')
    }

    // Create the food item via API
    await createFood({
      name: capitalizeName(newFood.value.name),
      foodGroup: newFood.value.foodGroup,
      packagingType: newFood.value.packagingType,
      storageLocation: newFood.value.storageLocation,
      expirationDate: newFood.value.expirationDate,
      daysInFridge: (newFood.value.timeInFridgeHours || 0) / 24,
      cumulativeTempAbuse: newFood.value.timeOutsideFridgeHours,
      freshnessScore: 100,
      daysUntilSpoilage: 7
    })
    
    // Refresh the list
    const updatedFoods = await loadFoodsFromCSV()
    const confirmedFoods = updatedFoods.filter(food => food.status === 'confirmed')
    cards.value = confirmedFoods.map(food => ({
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

onActivated(async () => {
  // Refresh confirmed cards when the user navigates back to this page
  const foods = await loadFoodsFromCSV()
  const confirmedFoods = foods.filter(food => food.status === 'confirmed')
  cards.value = confirmedFoods.map(food => ({ ...food, title: food.name }))

  window.addEventListener('keydown', handleKeyDown)

  // Poll for food data updates every 3 seconds
  cardsUpdateInterval = setInterval(async () => {
    const updatedFoods = await loadFoodsFromCSV()
    // Filter out non-confirmed items
    const confirmedUpdatedFoods = updatedFoods.filter(food => food.status === 'confirmed')
    const updatedCards = confirmedUpdatedFoods.map(food => ({
      ...food,
      title: food.name
    }))
    // Only update if data actually changed
    if (JSON.stringify(updatedCards) !== JSON.stringify(cards.value)) {
      cards.value = updatedCards
    }
  }, 3000)
})

onDeactivated(() => {
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

    <!-- Disambiguation cards — displayed side by side above the main grid -->
    <div v-if="disambiguationCards.length > 0" class="disambiguation-row">
      <div v-for="card in disambiguationCards" :key="'dis-' + card.id" class="disambiguation-card">
          <div class="disambiguation-header">
            <span class="disambiguation-icon">⚠️</span>
            <div>
              <h3 class="disambiguation-title">
                {{ card.disambiguationType === 'multi_confirmed'
                  ? 'Multiple matching items found'
                  : card.disambiguationType === 'multi_removed'
                    ? 'Multiple removed items match'
                    : card.disambiguationType === 'outgoing_or_new'
                      ? 'Existing item match — going out or new?'
                      : 'Returning item or another going out?' }}
              </h3>
              <p class="disambiguation-subtitle">
                {{ card.disambiguationType === 'multi_confirmed'
                  ? 'Which one is being taken out of the fridge?'
                  : card.disambiguationType === 'multi_removed'
                    ? 'Which one is returning to the fridge?'
                    : card.disambiguationType === 'outgoing_or_new'
                      ? 'Is this a brand-new item being added, or is the existing one going out?'
                      : 'Is one of these returning, or is a confirmed item being removed?' }}
              </p>
            </div>
          </div>

          <!-- Re-entry candidates -->
          <div v-if="card.removedMatches.length > 0" class="disambiguation-section">
            <div class="disambiguation-section-label">Recently removed — possible re-entry</div>
            <div
              v-for="removed in card.removedMatches"
              :key="removed.id"
              class="disambiguation-sub-card reentry-sub-card"
              :class="{
                'default-selected-reentry': removed.id === card.defaultReentryId && card.selectedAction === null,
                'user-selected-reentry': card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId
              }"
              @click="handleSubCardClick(removed, true)"
            >
              <div class="sub-card-info">
                <span class="sub-card-name">{{ removed.name }}</span>
                <span class="sub-card-detail">Outside: {{ removed.hoursOutside }}h</span>
                <span class="sub-card-detail">Freshness: {{ Math.round(removed.freshnessScore) }}</span>
              </div>
              <button
                class="sub-card-action-btn reentry-action-btn"
                :class="{
                  'btn-suggested': removed.id === card.defaultReentryId && card.selectedAction === null,
                  'btn-user-selected': card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId,
                  'btn-claimed': card.siblingClaimedRemovedIds.has(removed.id) && !(card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId)
                }"
                :disabled="card.siblingClaimedRemovedIds.has(removed.id) && !(card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId)"
                @click.stop="emit('resolveDisambiguation', card.id, 'mark_reentry', removed.id)"
              >{{
                card.siblingClaimedRemovedIds.has(removed.id) && !(card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId)
                  ? '⛔ Claimed by another scan'
                  : card.selectedAction === 'mark_reentry' && removed.id === card.selectedTargetId
                    ? '✓ Re-entry Selected'
                    : '↩ Mark as Re-entry'
              }}</button>
            </div>
          </div>

          <!-- Confirmed items in fridge -->
          <div v-if="card.confirmedMatches.length > 0" class="disambiguation-section">
            <div class="disambiguation-section-label">
              {{ card.disambiguationType === 'multi_confirmed' ? 'Select the item being removed:' : 'Or — mark a confirmed item as going out:' }}
            </div>
            <div
              v-for="match in card.confirmedMatches"
              :key="match.id"
              class="disambiguation-sub-card"
              :class="{
                'default-selected-outgoing': match.id === card.defaultOutgoingId && !card.defaultReentryId && card.selectedAction === null,
                'user-selected-outgoing': card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId
              }"
              @click="handleSubCardClick(match, false)"
            >
              <div class="sub-card-info">
                <span class="sub-card-name">{{ match.name }}</span>
                <span class="sub-card-detail">In fridge: {{ match.timeInFridge }}</span>
                <span class="sub-card-detail">Freshness: {{ Math.round(match.freshnessScore) }}</span>
              </div>
              <button
                class="sub-card-action-btn outgoing-action-btn"
                :class="{
                  'btn-suggested-outgoing': match.id === card.defaultOutgoingId && !card.defaultReentryId && card.selectedAction === null,
                  'btn-user-selected-outgoing': card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId,
                  'btn-claimed': card.siblingClaimedConfirmedIds.has(match.id) && !(card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId)
                }"
                :disabled="card.siblingClaimedConfirmedIds.has(match.id) && !(card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId)"
                @click.stop="emit('resolveDisambiguation', card.id, 'mark_outgoing', match.id)"
              >{{
                card.siblingClaimedConfirmedIds.has(match.id) && !(card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId)
                  ? '⛔ Claimed by another scan'
                  : card.selectedAction === 'mark_outgoing' && match.id === card.selectedTargetId
                    ? '✓ Selected'
                    : 'Select'
              }}</button>
            </div>
          </div>

          <button
            class="disambiguation-keep-new-btn"
            :class="{ 'keep-new-selected': card.selectedAction === 'keep_new' }"
            @click.stop="emit('resolveDisambiguation', card.id, 'keep_new', null)"
          >{{ card.selectedAction === 'keep_new' ? '✓ Keeping as New Item' : '+ Keep as New Item' }}</button>

          <button
            class="disambiguation-ok-btn"
            :disabled="!card.selectedAction"
            @click.stop="emit('okDisambiguation', card.id)"
          >OK</button>
        </div>

    </div>

    <!-- Cards Grid -->
    <div v-if="sortedCards.some(c => !c.isDisambiguation)" class="cards-grid">
      <template v-for="card in sortedCards">

        <!-- ── Disambiguation card (skip — rendered above) ── -->
        <template v-if="card.isDisambiguation" />

        <!-- ── Normal / Pending / Outgoing / Reentry card ── -->
        <div
          v-else
          :key="'card-' + card.id"
          class="card-item"
          :class="{ 'pending-card': card.isPending && !card.isReentry, 'reentry-card': card.isReentry, 'outgoing-card': card.isOutgoing }"
          :style="{ borderColor: card.isReentry ? 'oklch(0.55 0.18 200)' : card.isPending ? 'oklch(0.55 0.2 45)' : card.isOutgoing ? 'oklch(0.5 0.2 15)' : getFreshnessColor(card.freshnessScore) }"
          @click="handleCardClick(card.id)"
        >
          <div v-if="card.isPending && !card.isReentry" class="pending-badge">Pending</div>
          <div v-if="card.isReentry" class="reentry-badge">Re-entry</div>
          <div v-if="card.isOutgoing" class="outgoing-badge">Outgoing</div>
          <div class="card-header">
            <h3>{{ card.title }}</h3>
            <span v-if="card.isReentry" class="freshness-score" :style="{ color: getFreshnessColor(card.freshnessScore) }">{{ Math.round(card.freshnessScore) }}</span>
            <span v-else-if="!card.isPending && !card.isOutgoing" class="freshness-score" :style="{ color: getFreshnessColor(card.freshnessScore) }">{{ Math.round(card.freshnessScore) }}</span>
          </div>
          <p>Estimated days until spoilage: {{ card.daysUntilSpoilage }}</p>
          <p>Time in fridge: {{ card.timeInFridge }}</p>
          <!-- <p
            v-if="!card.isPending && !card.isOutgoing && !card.isReentry && card.cumulativeTempAbuse > 0"
            class="temp-abuse-line"
            :title="`${card.cumulativeTempAbuse.toFixed(1)}h at unsafe temperature (>${8}°C)`"
          >🌡️ Unsafe: {{ formatAbuseHours(card.cumulativeTempAbuse) }}</p> -->
          <button
            v-if="card.isOutgoing"
            class="keep-as-new-btn"
            @click.stop="emit('switchToIncoming', card.realId)"
          >Keep as New</button>
          <button
            v-if="card.isReentry"
            class="mark-as-new-btn"
            @click.stop="emit('markAsNew', card.realId)"
          >Mark as New Item</button>
        </div>

      </template>
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
            <button v-if="!isEditMode && !selectedCard?.isOutgoing && !selectedCard?.isReentry" class="edit-button" @click="enableEditMode" title="Edit food item">
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
              <option value="seafood">Seafood</option>
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
              <option value="opened">Opened</option>
              <option value="loose">Loose</option>
              <option value="canned">Canned</option>
              <option value="bottled">Bottled</option>
              <option value="boxed">Boxed</option>
              <option value="bagged">Bagged</option>
              <option value="wrapped">Wrapped</option>
            </select>
          </div>
          <div class="detail-item">
            <span class="detail-label">Storage:</span>
            <span v-if="!isEditMode" class="detail-value">{{ selectedCard.storageLocation === 'crisper' ? 'Crisper Drawer' : selectedCard.storageLocation === 'door' ? 'Door Shelf' : 'Regular Shelf' }}</span>
            <select v-else v-model="editedFood.storageLocation" class="edit-select">
              <option value="regular">Regular Shelf</option>
              <option value="crisper">Crisper Drawer</option>
              <option value="door">Door Shelf</option>
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

          <!-- Spoilage Rate + Expandable Factor Breakdown -->
          <div
            class="detail-item spoilage-rate-row"
            @click="showSpoilageBreakdown = !showSpoilageBreakdown"
            title="Click to see spoilage factors"
          >
            <span class="detail-label">Spoilage Rate:</span>
            <span class="detail-value spoilage-rate-value">
              {{
                selectedCard.spoilageMetadata?.effective_shelf_life
                  ? (100 / selectedCard.spoilageMetadata.effective_shelf_life).toFixed(2) + ' pts/day'
                  : '--'
              }}
              <span class="expand-icon">{{ showSpoilageBreakdown ? '▲' : '▼' }}</span>
            </span>
          </div>
          <div v-if="showSpoilageBreakdown && selectedCard.spoilageMetadata" class="spoilage-breakdown">
            <div class="breakdown-row">
              <span class="breakdown-label">Effective shelf life</span>
              <span class="breakdown-value">{{ selectedCard.spoilageMetadata.effective_shelf_life?.toFixed(1) }} days</span>
            </div>
            <div class="breakdown-row">
              <span class="breakdown-label">🌡️ Temperature factor</span>
              <span class="breakdown-value" :class="factorClass(selectedCard.spoilageMetadata.temp_factor)">
                × {{ selectedCard.spoilageMetadata.temp_factor?.toFixed(3) }}
                <span class="factor-note">{{ tempFactorStatus(selectedCard.spoilageMetadata.temp_factor) }}</span>
              </span>
            </div>
            <div class="breakdown-row">
              <span class="breakdown-label">💧 Humidity factor</span>
              <span class="breakdown-value" :class="factorClass(selectedCard.spoilageMetadata.humidity_factor)">
                × {{ selectedCard.spoilageMetadata.humidity_factor?.toFixed(3) }}
              </span>
            </div>
            <div class="breakdown-row">
              <span class="breakdown-label">⚠️ Abuse factor</span>
              <span class="breakdown-value" :class="factorClass(selectedCard.spoilageMetadata.abuse_factor)">
                × {{ selectedCard.spoilageMetadata.abuse_factor?.toFixed(3) }}
                <span class="factor-note">{{ abuseSummary(selectedCard.cumulativeTempAbuse, selectedCard.spoilageMetadata.temp_factor) }}</span>
              </span>
            </div>
            <div class="breakdown-row">
              <span class="breakdown-label">📦 Packaging factor</span>
              <span class="breakdown-value" :class="factorClass(selectedCard.spoilageMetadata.packaging_factor)">
                × {{ selectedCard.spoilageMetadata.packaging_factor?.toFixed(3) }}
              </span>
            </div>
            <div v-if="selectedCard.spoilageMetadata.gas_factor !== undefined" class="breakdown-row">
              <span class="breakdown-label">🧪 Gas factor</span>
              <span class="breakdown-value" :class="factorClass(selectedCard.spoilageMetadata.gas_factor)">
                × {{ selectedCard.spoilageMetadata.gas_factor?.toFixed(3) }}
                <span class="factor-note">{{ gasFactorStatus(selectedCard.spoilageMetadata) }}</span>
              </span>
            </div>
          </div>

          <div class="detail-item">
            <span class="detail-label">Time at Unsafe Temp:</span>
            <span class="detail-value" :style="{ color: (selectedCard.cumulativeTempAbuse ?? 0) >= 4 ? 'var(--color-critical, #e53e3e)' : (selectedCard.cumulativeTempAbuse ?? 0) > 0 ? 'var(--color-warning, #d97706)' : 'inherit' }">
              {{
                (selectedCard.cumulativeTempAbuse ?? 0) <= 0
                  ? 'None'
                  : (selectedCard.cumulativeTempAbuse ?? 0) < 1
                    ? `${Math.round((selectedCard.cumulativeTempAbuse ?? 0) * 60)} min`
                    : `${(selectedCard.cumulativeTempAbuse ?? 0).toFixed(1)} h`
              }}
            </span>
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
          <div v-if="!isEditMode && !selectedCard?.isOutgoing && !selectedCard?.isReentry" class="delete-section">
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
                <option value="seafood">Seafood</option>
                <option value="beverage">Beverage</option>
                <option value="condiment">Condiment</option>
                <option value="prepared">Prepared/Leftovers</option>
                <option value="other">Other</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="timeInFridgeHours">Time in Fridge (hours)</label>
              <input
                id="timeInFridgeHours"
                v-model.number="newFood.timeInFridgeHours"
                type="number"
                min="0"
                step="0.1"
              />
            </div>

            <div class="form-group">
              <label for="timeOutsideFridgeHours">Time Outside Fridge (hours)</label>
              <input
                id="timeOutsideFridgeHours"
                v-model.number="newFood.timeOutsideFridgeHours"
                type="number"
                min="0"
                step="0.1"
              />
            </div>
            
            <div class="form-group">
              <label for="packagingType">Packaging Type</label>
              <select id="packagingType" v-model="newFood.packagingType">
                <option value="sealed">Sealed</option>
                <option value="opened">Opened</option>
                <option value="loose">Loose</option>
                <option value="canned">Canned</option>
                <option value="bottled">Bottled</option>
                <option value="boxed">Boxed</option>
                <option value="bagged">Bagged</option>
                <option value="wrapped">Wrapped</option>
              </select>
            </div>
            
            <div class="form-group">
              <label for="storageLocation">Storage</label>
              <select id="storageLocation" v-model="newFood.storageLocation">
                <option value="regular">Regular Shelf</option>
                <option value="crisper">Crisper Drawer</option>
                <option value="door">Door Shelf</option>
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
          <p class="item-name">{{ selectedCard?.name }}</p>
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

/* Pending Card Styles */
.pending-card {
  background: linear-gradient(135deg, oklch(0.3 0.1 45) 0%, oklch(0.25 0.05 45) 100%);
  position: relative;
  border-width: 2px;
}

.pending-card:hover {
  background: linear-gradient(135deg, oklch(0.35 0.12 45) 0%, oklch(0.3 0.08 45) 100%);
}

.pending-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: oklch(0.55 0.2 45);
  color: oklch(0.95 0 0);
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  z-index: 1;
}

/* Outgoing Card Styles */
.outgoing-card {
  background: linear-gradient(135deg, oklch(0.3 0.1 15) 0%, oklch(0.25 0.05 15) 100%);
  position: relative;
  border-width: 2px;
}

.outgoing-card:hover {
  background: linear-gradient(135deg, oklch(0.35 0.12 15) 0%, oklch(0.3 0.08 15) 100%);
}

.outgoing-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: oklch(0.5 0.2 15);
  color: oklch(0.95 0 0);
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  z-index: 1;
}

.keep-as-new-btn {
  margin-top: 0.75rem;
  width: 100%;
  padding: 0.5rem 1rem;
  background: oklch(0.35 0.15 145);
  border: 1px solid oklch(0.5 0.2 145);
  border-radius: 6px;
  color: oklch(0.95 0 0);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.keep-as-new-btn:hover {
  background: oklch(0.4 0.18 145);
  transform: translateY(-1px);
}

/* Re-entry Card Styles */
.reentry-card {
  background: linear-gradient(135deg, oklch(0.28 0.08 200) 0%, oklch(0.23 0.04 200) 100%);
  position: relative;
  border-width: 2px;
}

.reentry-card:hover {
  background: linear-gradient(135deg, oklch(0.33 0.1 200) 0%, oklch(0.28 0.06 200) 100%);
}

.reentry-badge {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  background: oklch(0.5 0.18 200);
  color: oklch(0.95 0 0);
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  z-index: 1;
}

.mark-as-new-btn {
  margin-top: 0.75rem;
  width: 100%;
  padding: 0.5rem 1rem;
  background: oklch(0.3 0.08 200);
  border: 1px solid oklch(0.5 0.18 200);
  border-radius: 6px;
  color: oklch(0.95 0 0);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mark-as-new-btn:hover {
  background: oklch(0.36 0.1 200);
  transform: translateY(-1px);
}

/* ── Disambiguation card ── */
.disambiguation-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(20px, 300px));
  gap: 1.5rem;
  margin-top: 1rem;
  margin-bottom: 0;
  padding: 0 1rem;
  width: 100%;
}

.disambiguation-card {
  background: linear-gradient(135deg, oklch(0.22 0.04 275) 0%, oklch(0.18 0.03 275) 100%);
  border: 2px solid oklch(0.52 0.16 275);
  border-radius: 12px;
  padding: 1.25rem;
  position: relative;
  /* Match food-card sizing: min 2 cards wide, max 4 cards wide. */
  grid-column: span 4;
  width: 100%;
  min-width: min(100%, calc((300px * 2) + 1.5rem));
  max-width: calc((300px * 4) + (1.5rem * 3));
  justify-self: center;
}

.disambiguation-header {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.disambiguation-icon {
  font-size: 1.4rem;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.disambiguation-title {
  margin: 0 0 0.2rem 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: oklch(0.92 0 0);
}

.disambiguation-subtitle {
  margin: 0;
  font-size: 0.8rem;
  color: oklch(0.62 0 0);
}

.disambiguation-section {
  margin-bottom: 0.75rem;
}

.disambiguation-section-label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: oklch(0.58 0 0);
  margin-bottom: 0.4rem;
}

.disambiguation-sub-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: oklch(0.25 0.03 275);
  border: 1px solid oklch(0.38 0.07 275);
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.4rem;
  gap: 0.75rem;
  cursor: pointer;
  transition: filter 0.15s ease;
}

.disambiguation-sub-card:hover {
  filter: brightness(1.15);
}

.disambiguation-sub-card.default-selected-reentry {
  border-color: oklch(0.65 0.2 200) !important;
  background: oklch(0.26 0.09 200) !important;
  box-shadow: 0 0 0 2px oklch(0.55 0.18 200), 0 0 12px oklch(0.45 0.15 200 / 0.4);
}

.disambiguation-sub-card.default-selected-outgoing {
  border-color: oklch(0.65 0.2 30);
  background: oklch(0.26 0.07 30);
  box-shadow: 0 0 0 2px oklch(0.55 0.18 30), 0 0 12px oklch(0.45 0.15 30 / 0.4);
}

.suggested-badge {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-top: 0.1rem;
  align-self: flex-start;
}

.reentry-badge-pill {
  background: oklch(0.45 0.18 200);
  color: oklch(0.96 0 0);
}

.outgoing-badge-pill {
  background: oklch(0.45 0.18 30);
  color: oklch(0.96 0 0);
}

.btn-suggested {
  background: oklch(0.38 0.15 200) !important;
  border-color: oklch(0.6 0.2 200) !important;
  box-shadow: 0 0 8px oklch(0.5 0.18 200 / 0.5);
}

.btn-suggested-outgoing {
  background: oklch(0.38 0.15 30) !important;
  border-color: oklch(0.6 0.2 30) !important;
  box-shadow: 0 0 8px oklch(0.5 0.18 30 / 0.5);
}

/* User has actively chosen this card — solid ring, brighter than the 'suggested' glow */
.disambiguation-sub-card.user-selected-reentry {
  border-color: oklch(0.82 0.25 200) !important;
  background: oklch(0.33 0.13 200) !important;
  box-shadow: 0 0 0 3px oklch(0.7 0.24 200);
}

.disambiguation-sub-card.user-selected-outgoing {
  border-color: oklch(0.82 0.25 30);
  background: oklch(0.33 0.11 30);
  box-shadow: 0 0 0 3px oklch(0.7 0.24 30);
}

.btn-user-selected {
  background: oklch(0.56 0.23 200) !important;
  border-color: oklch(0.8 0.25 200) !important;
  color: oklch(0.98 0 0) !important;
  font-weight: 700;
}

.btn-user-selected-outgoing {
  background: oklch(0.56 0.23 30) !important;
  border-color: oklch(0.8 0.25 30) !important;
  color: oklch(0.98 0 0) !important;
  font-weight: 700;
}

.disambiguation-keep-new-btn.keep-new-selected {
  background: oklch(0.36 0.1 140);
  border-color: oklch(0.65 0.18 140);
  color: oklch(0.96 0 0);
  font-weight: 700;
}

.reentry-sub-card {
  border-color: oklch(0.5 0.15 200) !important;
  background: oklch(0.24 0.06 200) !important;
}

.sub-card-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  flex: 1;
  min-width: 0;
}

.sub-card-name {
  font-weight: 600;
  font-size: 0.88rem;
  color: oklch(0.92 0 0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sub-card-detail {
  font-size: 0.76rem;
  color: oklch(0.6 0 0);
}

.oldest-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 700;
  background: oklch(0.48 0.14 30);
  color: oklch(0.95 0 0);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-top: 0.1rem;
  align-self: flex-start;
}

.sub-card-action-btn {
  flex-shrink: 0;
  padding: 0.4rem 0.85rem;
  border-radius: 5px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid;
}

.outgoing-action-btn {
  background: oklch(0.27 0.07 15);
  border-color: oklch(0.5 0.2 15);
  color: oklch(0.92 0 0);
}

.outgoing-action-btn:hover:not(:disabled) {
  background: oklch(0.34 0.1 15);
  transform: translateY(-1px);
}

.reentry-action-btn {
  background: oklch(0.27 0.07 200);
  border-color: oklch(0.5 0.18 200);
  color: oklch(0.92 0 0);
}

.reentry-action-btn:hover:not(:disabled) {
  background: oklch(0.34 0.1 200);
  transform: translateY(-1px);
}

.btn-claimed {
  background: oklch(0.22 0.02 0) !important;
  border-color: oklch(0.35 0.02 0) !important;
  color: oklch(0.45 0 0) !important;
  cursor: not-allowed !important;
  font-style: italic;
}

.disambiguation-keep-new-btn {
  margin-top: 0.5rem;
  width: 100%;
  padding: 0.5rem 1rem;
  background: oklch(0.24 0.02 275);
  border: 1px solid oklch(0.4 0.06 275);
  border-radius: 6px;
  color: oklch(0.72 0 0);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.disambiguation-keep-new-btn:hover {
  background: oklch(0.3 0.04 275);
  color: oklch(0.92 0 0);
  border-color: oklch(0.52 0.1 275);
}

.disambiguation-ok-btn {
  margin-top: 0.75rem;
  width: 100%;
  padding: 0.6rem 1rem;
  background: oklch(0.55 0.18 145);
  border: none;
  border-radius: 6px;
  color: oklch(0.98 0 0);
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.disambiguation-ok-btn:hover:not(:disabled) {
  background: oklch(0.62 0.2 145);
  box-shadow: 0 2px 8px rgba(0, 200, 100, 0.3);
}

.disambiguation-ok-btn:disabled {
  background: oklch(0.28 0.02 145);
  color: oklch(0.5 0 0);
  cursor: not-allowed;
}

.confidence-badge {
  background: oklch(0.3 0 0);
  color: oklch(0.7 0.2 145);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.9rem;
  font-weight: 600;
  flex-shrink: 0;
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

/* Spoilage rate row */
.spoilage-rate-row {
  cursor: pointer;
  user-select: none;
}

.spoilage-rate-row:hover {
  background-color: oklch(0.2 0 0);
  border-radius: 4px;
}

.spoilage-rate-value {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.expand-icon {
  font-size: 0.7rem;
  color: oklch(0.6 0 0);
}

/* Spoilage factor breakdown panel */
.spoilage-breakdown {
  background-color: oklch(0.13 0 0);
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
  margin-bottom: 0.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.breakdown-row {
  display: flex;
  align-items: center;
  font-size: 0.875rem;
  gap: 0.5rem;
}

.breakdown-label {
  color: oklch(0.7 0 0);
  flex-shrink: 0;
}

.breakdown-value {
  font-weight: 600;
  font-size: 0.875rem;
  margin-left: auto;
  text-align: right;
}

.factor-good  { color: oklch(0.75 0.18 145); }  /* green */
.factor-warn  { color: oklch(0.78 0.18 75);  }  /* amber */
.factor-bad   { color: oklch(0.65 0.22 25);  }  /* red   */

.factor-note {
  display: block;
  font-size: 0.72rem;
  font-weight: 400;
  opacity: 0.85;
  text-align: right;
  margin-top: 0.1rem;
}

.temp-abuse-line {
  color: oklch(0.72 0.12 55);
  font-size: 0.8rem;
  margin-top: 0.25rem !important;
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

  .disambiguation-row {
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;
  }

  .disambiguation-card {
    grid-column: span 3;
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

  .disambiguation-row {
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
  }

  .disambiguation-card {
    grid-column: span 2;
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

  .disambiguation-row {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  .disambiguation-card {
    grid-column: span 1;
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
