<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getSensorData } from '../utils/sensorApi'
import { loadFoodsFromCSV } from '../utils/csvParser'
import { getWasteHistory, getTemperatureHistory, getMqHistory } from '../utils/statsApi'
import { MQ_SAFE_RANGES, classifyMqReading } from '../utils/mqSensorConfig'
import TemperatureChart from './TemperatureChart.vue'
import HumidityChart from './HumidityChart.vue'
import MqChart from './MqChart.vue'

defineProps({
  msg: String,
})

const count = ref(0)
const temperature = ref(4.0)
const humidity = ref(50.0)
const sensorsConnected = ref(false)
const foods = ref([])
const wasteHistory = ref([])
const temperatureHistory = ref([])
const mqHistory = ref([])

// Render only the most recent samples in charts for readability/performance.
// Full 12-hour history is still fetched/kept for monitoring and alerts.
const CHART_SAMPLE_LIMIT = 50

const temperatureChartData = computed(() =>
  temperatureHistory.value.slice(-CHART_SAMPLE_LIMIT)
)

const mqChartData = computed(() =>
  mqHistory.value.slice(-CHART_SAMPLE_LIMIT)
)

const SAFE_TEMP_MIN = 1
const SAFE_TEMP_MAX = 8
const SAFE_HUMIDITY_MIN = 20
const SAFE_HUMIDITY_MAX = 95

let sensorUpdateInterval
let foodsUpdateInterval
let historyUpdateInterval
let temperatureUpdateInterval
let mqUpdateInterval

// Computed statistics
const totalItems = computed(() => foods.value.length)

const expiringItems = computed(() => 
  foods.value.filter(food => food.daysUntilSpoilage > 0 && food.daysUntilSpoilage <= 2).length
)

const spoiledItems = computed(() => 
  foods.value.filter(food => food.freshnessScore <= 0).length
)

const averageFreshness = computed(() => {
  if (foods.value.length === 0) return 0
  const sum = foods.value.reduce((acc, food) => acc + food.freshnessScore, 0)
  return Math.round(sum / foods.value.length)
})

const categoryBreakdown = computed(() => {
  const categories = {}
  foods.value.forEach(food => {
    const category = food.foodGroup || 'other'
    categories[category] = (categories[category] || 0) + 1
  })
  return Object.entries(categories)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
})

const criticalAlerts = computed(() => 
  foods.value.filter(food => food.daysUntilSpoilage <= 1 || food.freshnessScore <= 15).length
)

const itemsSaved = computed(() => {
  // Calculate total items consumed in the last 7 days
  const last7Days = wasteHistory.value.slice(-7)
  return last7Days.reduce((sum, day) => sum + day.itemsConsumed, 0)
})

const wasteReduced = computed(() => {
  // Calculate waste percentage for last 7 days
  const last7Days = wasteHistory.value.slice(-7)
  const totalConsumed = last7Days.reduce((sum, day) => sum + day.itemsConsumed, 0)
  const totalWasted = last7Days.reduce((sum, day) => sum + day.itemsWasted, 0)
  const total = totalConsumed + totalWasted
  
  if (total === 0) return 0
  
  // Return percentage of items saved (not wasted)
  return Math.round((totalConsumed / total) * 100)
})

const getReadingStatusColor = (value, min, max, connected) => {
  if (!connected) return 'oklch(0.6 0 0)'
  return value >= min && value <= max ? '#228B22' : '#8B0000'
}

const mqStatusText = computed(() => {
  if (!sensorsConnected.value) return '--'
  const latest = mqHistory.value.length ? mqHistory.value[mqHistory.value.length - 1] : null
  if (!latest) return '--'

  let hasElevated = false
  for (const sensorId of Object.keys(MQ_SAFE_RANGES).map(Number)) {
    const status = classifyMqReading(sensorId, latest[`mq${sensorId}`])
    if (status === 'high') return 'High levels of gases detected'
    if (status === 'elevated') hasElevated = true
  }

  return hasElevated ? 'Elevated levels of gases detected' : 'No abnormal gases detected'
})

onMounted(async () => {
  // Fetch initial sensor data
  const sensorData = await getSensorData()
  temperature.value = sensorData.temperature
  humidity.value = sensorData.humidity
  sensorsConnected.value = sensorData.connected
  
  // Fetch initial food data
  foods.value = await loadFoodsFromCSV()
  
  // Fetch initial history data
  wasteHistory.value = await getWasteHistory()
  
  // Fetch initial temperature history
  temperatureHistory.value = await getTemperatureHistory()
  
  // Poll for sensor data updates every 0.5 seconds
  sensorUpdateInterval = setInterval(async () => {
    const sensorData = await getSensorData()
    temperature.value = sensorData.temperature
    humidity.value = sensorData.humidity
    sensorsConnected.value = sensorData.connected
  }, 500)
  
  // Poll for food data updates every 3 seconds
  foodsUpdateInterval = setInterval(async () => {
    const updatedFoods = await loadFoodsFromCSV()
    if (JSON.stringify(updatedFoods) !== JSON.stringify(foods.value)) {
      foods.value = updatedFoods
    }
  }, 3000)
  
  // Poll for history data updates every 30 seconds
  historyUpdateInterval = setInterval(async () => {
    wasteHistory.value = await getWasteHistory()
  }, 30000)
  
  // Poll for temperature history updates every 0.5 seconds
  temperatureUpdateInterval = setInterval(async () => {
    temperatureHistory.value = await getTemperatureHistory()
  }, 500)

  // Fetch initial MQ history
  mqHistory.value = await getMqHistory()

  // Poll for MQ history updates every 0.5 seconds
  mqUpdateInterval = setInterval(async () => {
    mqHistory.value = await getMqHistory()
  }, 500)
})

onUnmounted(() => {
  clearInterval(sensorUpdateInterval)
  clearInterval(foodsUpdateInterval)
  clearInterval(historyUpdateInterval)
  clearInterval(temperatureUpdateInterval)
  clearInterval(mqUpdateInterval)
})
</script>

<template>
<div class="stats-container">
  <h1 class="page-title">Fridge Statistics</h1>
  
  <div class="stats-grid">
    <!-- Sensor Readings Card -->
    <div class="stat-card sensor-card">
      <h2 class="card-title">Current Conditions</h2>
      <div class="sensor-readings">
        <div class="reading-with-chart">
          <div class="reading-large">
            <div class="reading-icon">🌡️</div>
            <div class="reading-content">
              <span class="reading-label">Temperature</span>
              <span class="reading-value-large" :style="{ color: getReadingStatusColor(temperature, SAFE_TEMP_MIN, SAFE_TEMP_MAX, sensorsConnected) }">{{ sensorsConnected ? temperature.toFixed(1) + '°C' : '--' }}</span>
            </div>
          </div>
          <TemperatureChart :data="temperatureChartData" />
        </div>
        <div class="reading-with-chart">
          <div class="reading-large">
            <div class="reading-icon">💧</div>
            <div class="reading-content">
              <span class="reading-label">Humidity</span>
              <span class="reading-value-large" :style="{ color: getReadingStatusColor(humidity, SAFE_HUMIDITY_MIN, SAFE_HUMIDITY_MAX, sensorsConnected) }">{{ sensorsConnected ? humidity.toFixed(1) + '%' : '--' }}</span>
            </div>
          </div>
          <HumidityChart :data="temperatureChartData" />
        </div>
      </div>
      <div class="reading-with-chart">
        <div class="reading-large">
          <div class="reading-icon">🧪</div>
          <div class="reading-content">
            <span class="reading-label">Gas Sensors (MQ)</span>
            <span class="reading-value-large" style="font-size: 1rem;">{{ mqStatusText }}</span>
          </div>
        </div>
        <MqChart :data="mqChartData" :connected="sensorsConnected" />
      </div>
      <div class="sensor-status">
        <span class="status-indicator" :class="{ active: sensorsConnected, disconnected: !sensorsConnected }"></span>
        <span class="status-text">{{ sensorsConnected ? 'Sensors Active' : 'Sensors Disconnected' }}</span>
      </div>
    </div>
    
    <!-- Food Overview Card -->
    <div class="stat-card">
      <h2 class="card-title">Food Overview</h2>
      <div class="stats-grid-inner">
        <div class="stat-item">
          <span class="stat-icon">📦</span>
          <div class="stat-details">
            <span class="stat-value">{{ totalItems }}</span>
            <span class="stat-label">Total Items</span>
          </div>
        </div>
        <div class="stat-item">
          <span class="stat-icon">⏰</span>
          <div class="stat-details">
            <span class="stat-value">{{ expiringItems }}</span>
            <span class="stat-label">Expiring Soon</span>
          </div>
        </div>
        <div class="stat-item">
          <span class="stat-icon">❌</span>
          <div class="stat-details">
            <span class="stat-value">{{ spoiledItems }}</span>
            <span class="stat-label">Spoiled</span>
          </div>
        </div>
        <div class="stat-item">
          <span class="stat-icon">⭐</span>
          <div class="stat-details">
            <span class="stat-value">{{ averageFreshness }}</span>
            <span class="stat-label">Avg Freshness</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Waste Reduction Card -->
    <div class="stat-card waste-card">
      <h2 class="card-title">Waste Reduction - Weekly Snapshot</h2>
      <div class="stats-grid-inner">
        <div class="stat-item">
          <span class="stat-icon">💚</span>
          <div class="stat-details">
            <span class="stat-value">{{ itemsSaved }}</span>
            <span class="stat-label">Items Saved</span>
          </div>
        </div>
        <div class="stat-item">
          <span class="stat-icon">📊</span>
          <div class="stat-details">
            <span class="stat-value">{{ wasteReduced }}%</span>
            <span class="stat-label">Waste Reduced</span>
          </div>
        </div>
        <div class="stat-item full-width">
          <div class="impact-message">
            <p v-if="itemsSaved > 0">
              🎉 Great job! You've consumed {{ itemsSaved }} item{{ itemsSaved !== 1 ? 's' : '' }} 
              in the last 7 days, preventing waste!
            </p>
            <p v-else-if="totalItems > 0">
              📊 Start tracking item outcomes to see your waste reduction progress!
            </p>
            <p v-else>
              📝 Add items to your inventory to start tracking waste reduction.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</template>

<style scoped>
.stats-container {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  font-size: 2.5rem;
  margin-bottom: 2rem;
  color: oklch(0.9 0 0);
  text-align: left;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .sensor-card {
    grid-column: span 1;
  }
}

.stat-card {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 1.5rem;
}

.sensor-card {
  grid-column: span 2;
}

.card-title {
  font-size: 1.5rem;
  margin: 0 0 1.5rem 0;
  color: oklch(0.9 0 0);
}

.sensor-readings {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.reading-with-chart {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.reading-large {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  background-color: oklch(0.15 0 0);
  border-radius: 8px;
  border: 1px solid oklch(0.3 0 0);
}

.reading-icon {
  font-size: 2.5rem;
  flex-shrink: 0;
}

.reading-content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.reading-label {
  color: oklch(0.7 0 0);
  font-size: 0.9rem;
  font-weight: 500;
}

.reading-value-large {
  color: oklch(0.9 0 0);
  font-size: 2rem;
  font-weight: 700;
  line-height: 1;
}

.sensor-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background-color: oklch(0.15 0 0);
  border-radius: 6px;
  margin-top: 1rem;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: #666;
}

.status-indicator.active {
  background-color: #00FF00;
  box-shadow: 0 0 8px #00FF00;
  animation: pulse 2s infinite;
}

.status-indicator.disconnected {
  background-color: #FF0000;
  box-shadow: 0 0 8px #FF0000;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

.status-text {
  color: oklch(0.8 0 0);
  font-size: 0.9rem;
}

.placeholder-text {
  color: oklch(0.6 0 0);
  font-style: italic;
  text-align: center;
  padding: 2rem;
}

.stats-grid-inner {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  padding: 0.5rem 1rem;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background-color: oklch(0.15 0 0);
  border-radius: 8px;
  border: 1px solid oklch(0.3 0 0);
  min-height: 60px;
}

.stat-item.full-width {
  grid-column: span 2;
  flex-direction: column;
  align-items: flex-start;
}

.stat-icon {
  font-size: 1.75rem;
  flex-shrink: 0;
}

.stat-details {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.stat-value {
  color: oklch(0.9 0 0);
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1;
}

.stat-label {
  color: oklch(0.7 0 0);
  font-size: 0.85rem;
  font-weight: 500;
}

.category-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.category-badge {
  background-color: oklch(0.25 0 0);
  color: oklch(0.85 0 0);
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.8rem;
  border: 1px solid oklch(0.4 0 0);
}

.impact-message,
.trend-message {
  width: 100%;
}

.impact-message p,
.trend-message p {
  margin: 0;
  color: oklch(0.8 0 0);
  font-size: 0.9rem;
  line-height: 1.5;
}

.chart-item {
  padding: 0;
  background-color: transparent;
  border: none;
}

@media (max-width: 768px) {
  .stats-container {
    padding: 1rem;
  }
  
  .page-title {
    font-size: 2rem;
  }
  
  .sensor-card {
    grid-column: span 1;
  }
  
  .reading-large {
    padding: 1rem;
  }
  
  .reading-icon {
    font-size: 2rem;
  }
  
  .reading-value-large {
    font-size: 1.5rem;
  }
  
  .stats-grid-inner {
    grid-template-columns: 1fr;
  }
  
  .stat-item.full-width {
    grid-column: span 1;
  }
}
</style>
