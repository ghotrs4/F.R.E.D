<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { loadFoodsFromCSV } from '../utils/csvParser'
import { getSensorData } from '../utils/sensorApi'
import { getWasteHistory, getTemperatureHistory } from '../utils/statsApi'

const router = useRouter()

defineProps({
  msg: String,
})

const count = ref(0)
const showAlertsPopup = ref(false)
const greeting = ref('Good Morning')
const foods = ref([])
const temperature = ref(4.0)
const humidity = ref(50.0)
const sensorConnected = ref(false)
const wasteHistory = ref([])
const recipes = ref([])
const loadingRecipes = ref(false)
const temperatureHistory = ref([])

const SAFE_TEMP_MIN = 1
const SAFE_TEMP_MAX = 8
const SAFE_HUMIDITY_MIN = 20
const SAFE_HUMIDITY_MAX = 95
const ENV_ALERT_MIN_MINUTES = 10

const wasteReduced = computed(() => {
  const last7Days = wasteHistory.value.slice(-7)
  const totalConsumed = last7Days.reduce((sum, day) => sum + day.itemsConsumed, 0)
  const totalWasted = last7Days.reduce((sum, day) => sum + day.itemsWasted, 0)
  const total = totalConsumed + totalWasted
  
  if (total === 0) return 0
  return Math.round((totalConsumed / total) * 100)
})

const getGreeting = () => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good Morning'
  if (hour < 18) return 'Good Afternoon'
  return 'Good Evening'
}

// Get the 5 foods with lowest freshness scores
const lowestFreshnessFoods = computed(() => {
  return [...foods.value]
    .sort((a, b) => a.freshnessScore - b.freshnessScore)
    .slice(0, 5)
})

// Generate alerts based on food conditions
const foodAlerts = computed(() => {
  const alertList = []
  
  foods.value.forEach(food => {
    // If food has spoiled (freshness score 0), only show spoiled alert
    if (food.freshnessScore <= 0) {
      alertList.push({
        type: 'critical',
        message: `${food.name} has likely spoiled! Check and discard immediately.`,
        food: food
      })
      return // Skip other alerts for this food
    }
    
    if (food.daysUntilSpoilage <= 1) {
      const message = food.daysUntilSpoilage === 0
        ? `${food.name} will likely start to spoil in the next 24 hours!`
        : `${food.name} will spoil in ${food.daysUntilSpoilage} day${food.daysUntilSpoilage !== 1 ? 's' : ''}!`
      alertList.push({
        type: 'critical',
        message: message,
        food: food
      })
    } else if (food.daysUntilSpoilage === 2) {
      alertList.push({
        type: 'warning',
        message: `${food.name} will spoil in ${food.daysUntilSpoilage} days.`,
        food: food
      })
    }
    
    if (food.freshnessScore < 15) {
      alertList.push({
        type: 'warning',
        message: `${food.name} has low freshness (${Math.round(food.freshnessScore)}/100).`,
        food: food
      })
    }
  })
  
  return alertList
})

const formatDuration = (minutes) => {
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  if (mins === 0) return `${hours}h`
  return `${hours}h ${mins}m`
}

const formatDeviation = (amount, unit) => {
  return `${amount.toFixed(1)}${unit}`
}

const summarizeOutOfRange = (entries, key, min, max) => {
  if (!entries.length) return null

  let totalMinutes = 0
  let maxDeviation = 0
  let direction = ''

  for (let i = 0; i < entries.length; i += 1) {
    const current = entries[i]
    const value = current[key]
    if (value == null) continue

    let deviation = 0
    let sampleDirection = ''
    if (value < min) {
      deviation = min - value
      sampleDirection = 'below'
    } else if (value > max) {
      deviation = value - max
      sampleDirection = 'above'
    }

    if (deviation <= 0) continue

    maxDeviation = Math.max(maxDeviation, deviation)
    if (!direction || deviation >= maxDeviation) {
      direction = sampleDirection
    }

    if (i < entries.length - 1) {
      const currentTs = new Date(current.timestamp)
      const nextTs = new Date(entries[i + 1].timestamp)
      const deltaMinutes = Math.max(0, (nextTs - currentTs) / 60000)
      totalMinutes += deltaMinutes
    }
  }

  if (totalMinutes < ENV_ALERT_MIN_MINUTES) return null

  return { totalMinutes, maxDeviation, direction }
}

const environmentAlerts = computed(() => {
  const entries = [...temperatureHistory.value].sort(
    (a, b) => new Date(a.timestamp) - new Date(b.timestamp)
  )

  const tempSummary = summarizeOutOfRange(entries, 'temperature', SAFE_TEMP_MIN, SAFE_TEMP_MAX)
  const humiditySummary = summarizeOutOfRange(entries, 'humidity', SAFE_HUMIDITY_MIN, SAFE_HUMIDITY_MAX)

  const result = []

  if (tempSummary) {
    result.push({
      type: 'critical',
      category: 'environment',
      message: `Temperature was outside the safe range for ${formatDuration(tempSummary.totalMinutes)} in the last 12 hours, peaking ${tempSummary.direction} the limit by ${formatDeviation(tempSummary.maxDeviation, '°C')}.`,
      details: `Safe range: ${SAFE_TEMP_MIN}-${SAFE_TEMP_MAX}°C`
    })
  }

  if (humiditySummary) {
    result.push({
      type: 'warning',
      category: 'environment',
      message: `Humidity was outside the safe range for ${formatDuration(humiditySummary.totalMinutes)} in the last 12 hours, peaking ${humiditySummary.direction} the limit by ${formatDeviation(humiditySummary.maxDeviation, '%')}.`,
      details: `Safe range: ${SAFE_HUMIDITY_MIN}-${SAFE_HUMIDITY_MAX}%`
    })
  }

  return result
})

const alerts = computed(() => [...environmentAlerts.value, ...foodAlerts.value])

const handleFoodClick = (foodId) => {
  console.log(`Food ${foodId} clicked`)
}

const handleCardClick = (cardId) => {
  console.log(`Card ${cardId} clicked`)
}

const navigateToRecipes = () => {
  router.push('/recipes')
}

const stripHtml = (html) => {
  const tmp = document.createElement('div')
  tmp.innerHTML = html
  return tmp.textContent || tmp.innerText || ''
}

const getFreshnessColor = (score) => {
  if (score <= 15) return '#8B0000' // Dark red
  if (score > 15 && score <= 39) return '#FF6B6B' // Light red
  if (score > 39 && score <= 59) return '#FFD700' // Yellow
  if (score > 59 && score <= 84) return '#ADFF2F' // Yellow-green (lighter and more yellow)
  if (score > 84) return '#228B22' // Forest green (lighter than dark green)
  return '#D3D3D3' // Default gray
}

const getReadingStatusColor = (value, min, max, connected) => {
  if (!connected) return 'oklch(0.6 0 0)'
  return value >= min && value <= max ? '#228B22' : '#8B0000'
}

const navigateToInventory = () => {
  router.push('/inventory')
}

const navigateToStats = () => {
  router.push('/stats')
}

const openAlertsPopup = () => {
  showAlertsPopup.value = true
}

const closeAlertsPopup = () => {
  showAlertsPopup.value = false
}

const handleKeyDown = (event) => {
  if (event.key === 'Escape') {
    showAlertsPopup.value = false
  }
}

let greetingInterval
let foodsUpdateInterval
let sensorUpdateInterval
let historyUpdateInterval
let temperatureHistoryUpdateInterval

const handleFoodAdded = async () => {
  // Refresh foods list when a new item is added via global scanner
  foods.value = await loadFoodsFromCSV()
}

onMounted(async () => {
  greeting.value = getGreeting()
  foods.value = await loadFoodsFromCSV()
  
  // Listen for food-added event from global scanner
  window.addEventListener('food-added', handleFoodAdded)
  
  // Fetch initial sensor data
  const sensorData = await getSensorData()
  temperature.value = sensorData.temperature
  humidity.value = sensorData.humidity
  sensorConnected.value = sensorData.connected
  
  // Fetch initial history data
  wasteHistory.value = await getWasteHistory()
  temperatureHistory.value = await getTemperatureHistory()
  
  // Load recipes from localStorage (no API calls)
  // Recipes are cached by the Recipes page
  try {
    const cachedRecipes = localStorage.getItem('cachedRecipes')
    if (cachedRecipes) {
      const allRecipes = JSON.parse(cachedRecipes)
      recipes.value = allRecipes.slice(0, 3)
    } else {
      recipes.value = []
    }
  } catch (e) {
    console.error('Error loading cached recipes:', e)
    recipes.value = []
  }
  
  window.addEventListener('keydown', handleKeyDown)
  
  // Update greeting every minute
  greetingInterval = setInterval(() => {
    greeting.value = getGreeting()
  }, 60000)
  
  // Poll for food data updates every 3 seconds
  foodsUpdateInterval = setInterval(async () => {
    const updatedFoods = await loadFoodsFromCSV()
    // Only update if data actually changed
    if (JSON.stringify(updatedFoods) !== JSON.stringify(foods.value)) {
      foods.value = updatedFoods
    }
  }, 3000)
  
  // Poll for sensor data updates every 5 seconds
  sensorUpdateInterval = setInterval(async () => {
    const sensorData = await getSensorData()
    temperature.value = sensorData.temperature
    humidity.value = sensorData.humidity
    sensorConnected.value = sensorData.connected
  }, 5000)
  
  // Poll for history data updates every 30 seconds
  historyUpdateInterval = setInterval(async () => {
    wasteHistory.value = await getWasteHistory()
  }, 30000)

  temperatureHistoryUpdateInterval = setInterval(async () => {
    temperatureHistory.value = await getTemperatureHistory()
  }, 30000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('food-added', handleFoodAdded)
  clearInterval(greetingInterval)
  clearInterval(foodsUpdateInterval)
  clearInterval(sensorUpdateInterval)
  clearInterval(historyUpdateInterval)
  clearInterval(temperatureHistoryUpdateInterval)
})
</script>

<template>
<div class="content">
  <h1 class="welcome">{{ greeting }}</h1>
  <p class="subtitle">Your Fridge at a Glance</p>
  
  <div class="sections">
    <section class="section" @click="navigateToInventory">
      <h2>Inventory</h2>
      <div v-if="lowestFreshnessFoods.length === 0" class="empty-inventory">
        <p>No items to display</p>
      </div>
      <div v-else class="inventory-list">
        <div 
          v-for="food in lowestFreshnessFoods" 
          :key="food.id"
          class="food-item"
          :style="{ borderColor: getFreshnessColor(food.freshnessScore) }"
        >
          <span class="food-name">{{ food.name }}</span>
          <span 
            class="freshness-score" 
            :style="{ color: getFreshnessColor(food.freshnessScore) }"
          >{{ Math.round(food.freshnessScore) }}</span>
        </div>
      </div>
    </section>
    
    <section class="section" @click="navigateToStats">
      <h2>Stats</h2>
      <div class="sensor-readings">
        <div class="reading-item">
          <span class="reading-label">Sensor Status</span>
          <span class="reading-value" :style="{ color: sensorConnected ? '#228B22' : '#8B0000' }">{{ sensorConnected ? 'Active' : 'Disconnected' }}</span>
        </div>
        <div class="reading-item">
          <span class="reading-label">Temperature</span>
          <span class="reading-value" :style="{ color: getReadingStatusColor(temperature, SAFE_TEMP_MIN, SAFE_TEMP_MAX, sensorConnected) }">{{ sensorConnected ? temperature.toFixed(1) + '°C' : '--' }}</span>
        </div>
        <div class="reading-item">
          <span class="reading-label">Humidity</span>
          <span class="reading-value" :style="{ color: getReadingStatusColor(humidity, SAFE_HUMIDITY_MIN, SAFE_HUMIDITY_MAX, sensorConnected) }">{{ sensorConnected ? humidity.toFixed(1) + '%' : '--' }}</span>
        </div>
        <div class="reading-item">
          <span class="reading-label">Waste Reduced</span>
          <span class="reading-value">{{ wasteReduced }}%</span>
        </div>
      </div>
    </section>
    
    <section class="section recipes-section" @click="navigateToRecipes">
      <h2>Recipes</h2>
      <p class="section-subtitle">Top recipes from your recipe page</p>
      <div v-if="loadingRecipes" class="loading-recipes">
        Loading recipes...
      </div>
      <div v-else-if="recipes.length === 0" class="no-recipes">
        No recipes available with current filters. Visit the Recipes page to adjust your filters or add ingredients to your inventory!
      </div>
      <div v-else class="recipes-grid-home">
        <div v-for="recipe in recipes" :key="recipe.id" class="recipe-card-home">
          <h3>{{ recipe.title }}</h3>
        </div>
      </div>
      <div class="view-all-hint">Click to view all recipes →</div>
    </section>
  </div>
  
  <div class="alerts-row">
    <section class="section alerts-section" @click="openAlertsPopup">
      <h2>Alerts</h2>
      <div class="alerts-content">
        <div v-if="alerts.length === 0" class="no-alerts">
          ✅ No alerts at this time. All your food is in good condition!
        </div>
        <div v-else class="alerts-list-inline">
          <div 
            v-for="(alert, index) in alerts.slice(0, 3)" 
            :key="index"
            class="alert-item-inline"
            :class="alert.type"
          >
            <div class="alert-icon">
              <span v-if="alert.type === 'critical'">⚠️</span>
              <span v-else>🔔</span>
            </div>
            <div class="alert-text">
              <div class="alert-message">{{ alert.message }}</div>
            </div>
          </div>
          <div v-if="alerts.length > 3" class="more-alerts">
            +{{ alerts.length - 3 }} more alert{{ alerts.length - 3 !== 1 ? 's' : '' }} - Click to view all
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- Alerts Popup -->
  <div v-if="showAlertsPopup" class="popup-overlay" @click="closeAlertsPopup">
    <div class="popup-content" @click.stop>
      <div class="popup-header">
        <h2>Food Alerts</h2>
        <button class="close-button" @click="closeAlertsPopup">&times;</button>
      </div>
      <div class="popup-body">
        <div v-if="alerts.length === 0" class="no-alerts-message">
          <p>No alerts at this time. All your food is in good condition!</p>
        </div>
        <div v-else class="alerts-list">
          <div
            v-for="(alert, index) in alerts"
            :key="index"
            class="alert-item"
            :class="alert.type"
          >
            <div class="alert-icon">
              <span v-if="alert.type === 'critical'">⚠️</span>
              <span v-else>🔔</span>
            </div>
            <div class="alert-content">
              <p class="alert-message">{{ alert.message }}</p>
              <div class="alert-details">
                <template v-if="alert.food">
                  <span>Freshness: {{ Math.round(alert.food.freshnessScore) }}/100</span>
                  <span>•</span>
                  <span>Days left: {{ alert.food.daysUntilSpoilage }}</span>
                </template>
                <template v-else-if="alert.details">
                  <span>{{ alert.details }}</span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.content {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
  padding: 2rem;
  text-align: center;
}

.sections {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  justify-content: center;
  gap: 2rem;
  width: 100%;
  margin-top: 2rem;
  padding: 0 1rem;
}

.alerts-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  width: 100%;
  margin-top: 2rem;
  padding: 0 1rem;
}

.section {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
  flex: 1;
  min-width: 250px;
  max-width: 300px;
}

.alerts-section {
  width: 100%;
  max-width: calc(900px + 4rem);
}

.section:hover {
  background-color: oklch(0.25 0 0);
  border-color: oklch(0.55 0.15 265);
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.section h2 {
  margin: 0 0 1rem 0;
  font-size: 1.5rem;
  color: oklch(0.9 0 0);
  word-break: break-word;
  overflow-wrap: break-word;
}

.inventory-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sensor-readings {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background-color: oklch(0.15 0 0);
  border-radius: 8px;
}

.reading-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reading-label {
  color: oklch(0.7 0 0);
  font-size: 0.9rem;
}

.reading-value {
  color: oklch(0.9 0 0);
  font-size: 1.1rem;
  font-weight: 600;
}

.empty-inventory {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100px;
  padding: 2rem;
}

.empty-inventory p {
  font-size: 1rem;
  color: oklch(0.6 0 0);
  font-weight: 500;
}

.food-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background-color: oklch(0.25 0 0);
  border: 1px solid;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.food-name {
  font-weight: 500;
  font-size: 1rem;
  flex: 1;
  word-wrap: break-word;
  overflow-wrap: break-word;
  min-width: 0;
}

.freshness-score {
  font-size: 0.875rem;
  font-weight: 600;
  margin-left: 10px;
}

.welcome {
  font-size: clamp(1.5rem, 5vw, 3rem);
}

.subtitle {
  color: #888;
  font-size: clamp(0.875rem, 2vw, 1.25rem);
}

/* Alerts Section Styles */
.alerts-section {
  border-color: #FF6B6B;
}

.alerts-content {
  padding: 1rem 0;
}

.no-alerts {
  text-align: center;
  color: oklch(0.7 0 0);
  font-style: italic;
  padding: 1rem;
}

.alerts-list-inline {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.alert-item-inline {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border-radius: 6px;
  border-left: 3px solid;
}

.alert-item-inline.critical {
  background-color: rgba(139, 0, 0, 0.1);
  border-left-color: #8B0000;
}

.alert-item-inline.warning {
  background-color: rgba(255, 107, 107, 0.1);
  border-left-color: #FF6B6B;
}

.alert-icon {
  font-size: 1.2rem;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.alert-text {
  flex: 1;
}

.alert-message {
  color: oklch(0.9 0 0);
  font-size: 0.9rem;
  line-height: 1.4;
  word-break: break-word;
  overflow-wrap: break-word;
}

.more-alerts {
  text-align: center;
  color: oklch(0.7 0 0);
  font-size: 0.85rem;
  font-style: italic;
  padding: 0.5rem;
  border-top: 1px solid oklch(0.2 0 0);
  margin-top: 0.5rem;
}

/* Alerts Popup Styles */
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
  max-width: 600px;
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

.popup-header h2 {
  margin: 0;
  color: oklch(0.9 0 0);
  font-size: 1.5rem;
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

.no-alerts-message {
  text-align: center;
  color: oklch(0.7 0 0);
  font-style: italic;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 1rem;
  border-radius: 8px;
  border-left: 4px solid;
}

.alert-item.critical {
  background-color: rgba(139, 0, 0, 0.1);
  border-left-color: #8B0000;
}

.alert-item.warning {
  background-color: rgba(255, 107, 107, 0.1);
  border-left-color: #FF6B6B;
}

.alert-icon {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.alert-content {
  flex: 1;
}

.alert-message {
  margin: 0 0 0.5rem 0;
  color: oklch(0.9 0 0);
  font-weight: 500;
  text-align: left;
}

.alert-details {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  color: oklch(0.7 0 0);
  font-size: 0.875rem;
  text-align: left;
}

/* Responsive Design - Tablet */
@media (max-width: 1024px) {
  .home-container {
    padding: 1.5rem;
  }

  .sections-container {
    flex-direction: column;
  }

  .section {
    width: 100%;
  }
}

/* Responsive Design - Mobile */
@media (max-width: 768px) {
  .home-container {
    padding: 1rem;
  }

  .greeting {
    font-size: 1.75rem;
  }

  .see-all-button {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
  }

  .food-item {
    padding: 0.5rem 1rem;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .food-name {
    font-size: 0.95rem;
  }

  .freshness-score {
    align-self: flex-end;
  }

  .alert-item {
    padding: 0.75rem;
  }

  .alert-message {
    font-size: 0.9rem;
  }

  .alert-details {
    font-size: 0.8rem;
    flex-wrap: wrap;
  }
}

/* Responsive Design - Small Mobile */
@media (max-width: 480px) {
  .home-container {
    padding: 0.75rem;
  }

  .greeting {
    font-size: 1.5rem;
  }

  .section h2 {
    font-size: 1.25rem;
  }

  .food-item {
    padding: 0.5rem 0.75rem;
  }

  .food-name {
    font-size: 0.875rem;
  }

  .freshness-score {
    font-size: 0.8rem;
  }

  .see-all-button {
    width: 100%;
    padding: 0.75rem;
  }
  
  .header-row {
    flex-direction: column;
    gap: 1rem;
  }
  
  .header-content {
    text-align: center;
  }
  
  .scan-button {
    width: 100%;
  }
}

/* Improve touch targets for mobile */
@media (hover: none) and (pointer: coarse) {
  .food-item,
  .see-all-button,
  .alert-item {
    min-height: 44px;
  }

  .see-all-button {
    padding: 0.75rem 1.25rem;
  }
}

/* Recipes Section */
.recipes-section {
  /* Extends across multiple columns in the grid */
  grid-column: 1 / -1;
}

.section-subtitle {
  margin: -0.5rem 0 1rem 0;
  color: oklch(0.6 0 0);
  font-size: 0.95rem;
}

.loading-recipes,
.no-recipes {
  padding: 2rem;
  color: oklch(0.6 0 0);
  font-size: 1rem;
}

.recipes-grid-home {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 1rem;
}

.recipe-card-home {
  background-color: oklch(0.15 0 0);
  border: 1px solid oklch(0.35 0 0);
  border-radius: 8px;
  padding: 1rem;
  overflow: hidden;
}

.recipe-card-home h3 {
  margin: 0;
  font-size: 1rem;
  color: oklch(0.85 0 0);
  line-height: 1.3;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.recipe-meta-home {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  color: oklch(0.65 0 0);
}

.ingredients-match-home {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}

.used-ingredients {
  color: oklch(0.7 0.15 160);
}

.missed-ingredients {
  color: oklch(0.7 0.15 40);
}

.recipe-summary-home {
  color: oklch(0.6 0 0);
  font-size: 0.875rem;
  line-height: 1.4;
  margin-top: 0.5rem;
}

.view-all-hint {
  margin-top: 1rem;
  color: oklch(0.55 0.15 265);
  font-size: 0.9rem;
  font-weight: 500;
  text-align: center;
}

@media (max-width: 768px) {
  .recipe-card-home h3 {
    font-size: 0.95rem;
  }
}
</style>
