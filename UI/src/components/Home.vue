<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { loadFoodsFromCSV } from '../utils/csvParser'
import Stats from './Stats.vue'
import Recipes from './Recipes.vue'

const router = useRouter()

defineProps({
  msg: String,
})

const count = ref(0)
const showAlertsPopup = ref(false)
const greeting = ref('Good Morning')
const foods = ref([])

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
const alerts = computed(() => {
  const alertList = []
  
  foods.value.forEach(food => {
    if (food.daysUntilSpoilage <= 1) {
      alertList.push({
        type: 'critical',
        message: `${food.name} will spoil in ${food.daysUntilSpoilage} day${food.daysUntilSpoilage !== 1 ? 's' : ''}!`,
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
        message: `${food.name} has low freshness (${food.freshnessScore}/100).`,
        food: food
      })
    }
  })
  
  return alertList
})

const handleFoodClick = (foodId) => {
  console.log(`Food ${foodId} clicked`)
}

const handleCardClick = (cardId) => {
  console.log(`Card ${cardId} clicked`)
}

const getFreshnessColor = (score) => {
  if (score <= 15) return '#8B0000' // Dark red
  if (score >= 16 && score <= 39) return '#FF6B6B' // Light red
  if (score >= 40 && score <= 59) return '#FFD700' // Yellow
  if (score >= 60 && score <= 84) return '#ADFF2F' // Yellow-green (lighter and more yellow)
  if (score >= 85) return '#228B22' // Forest green (lighter than dark green)
  return '#D3D3D3' // Default gray
}

const navigateToInventory = () => {
  router.push('/inventory')
}

const navigateToStats = () => {
  router.push('/stats')
}

const navigateToRecipes = () => {
  router.push('/recipes')
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

onMounted(async () => {
  greeting.value = getGreeting()
  foods.value = await loadFoodsFromCSV()
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
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  clearInterval(greetingInterval)
  clearInterval(foodsUpdateInterval)
})
</script>

<template>
<div class="content">
  <h1 class="welcome">{{ greeting }}</h1>
  <p class="subtitle">Your Fridge at a Glance</p>
  <p>2&deg;C | 30% humidity</p>
  
  <div class="sections">
    <section class="section" @click="navigateToInventory">
      <h2>Inventory</h2>
      <div class="inventory-list">
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
          >{{ food.freshnessScore }}</span>
        </div>
      </div>
    </section>
    
    <section class="section" @click="navigateToStats">
      <h2>Stats</h2>
      <Stats />
    </section>
    
    <section class="section" @click="navigateToRecipes">
      <h2>Recipes</h2>
      <Recipes />
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
                <span>Freshness: {{ alert.food.freshnessScore }}/100</span>
                <span>•</span>
                <span>Days left: {{ alert.food.daysUntilSpoilage }}</span>
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
  justify-content: center;
  gap: 2rem;
  width: 100%;
  max-width: 1200px;
  margin-top: 2rem;
}

.alerts-row {
  display: flex;
  justify-content: center;
  width: 100%;
  max-width: 1200px;
  margin-top: 2rem;
}

.alerts-section {
  width: 100%;
}

.section {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
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
}

.inventory-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
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
</style>
