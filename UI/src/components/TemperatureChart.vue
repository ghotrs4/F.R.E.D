<template>
  <div class="temperature-chart">
    <div v-if="data.length === 0" class="no-data">
      <p>No data available</p>
    </div>
    <div v-else class="chart-container">
      <div class="chart-area">
        <div class="y-axis">
          <span class="y-label">{{ maxTemp.toFixed(1) }}°C</span>
          <span class="y-label">{{ ((maxTemp + minTemp) / 2).toFixed(1) }}°C</span>
          <span class="y-label">{{ minTemp.toFixed(1) }}°C</span>
        </div>
        <div class="chart-content">
          <svg :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`" preserveAspectRatio="none">
            <!-- Optimal fridge temperature band: 1–4 °C -->
            <rect
              v-if="optimalBand.height > 0"
              x="0"
              :y="optimalBand.y"
              :width="viewBoxWidth"
              :height="optimalBand.height"
              fill="rgba(0,200,100,0.10)"
            />
            <line
              v-if="optimalBand.height > 0"
              x1="0" :y1="optimalBand.y"
              :x2="viewBoxWidth" :y2="optimalBand.y"
              stroke="rgba(0,200,100,0.45)" stroke-width="1.5" stroke-dasharray="6,4"
            />
            <line
              v-if="optimalBand.height > 0"
              x1="0" :y1="optimalBand.y + optimalBand.height"
              :x2="viewBoxWidth" :y2="optimalBand.y + optimalBand.height"
              stroke="rgba(0,200,100,0.45)" stroke-width="1.5" stroke-dasharray="6,4"
            />
            <!-- Temperature line -->
            <polyline
              :points="temperaturePoints"
              fill="none"
              stroke="#FF6B35"
              stroke-width="3"
              class="temp-line"
            />
            <!-- Temperature points -->
            <circle
              v-for="(point, index) in temperatureData"
              :key="`temp-${index}`"
              :cx="point.x"
              :cy="point.y"
              r="4"
              fill="#FF6B35"
              class="data-point"
            >
              <title>{{ point.label }}: {{ point.value.toFixed(1) }}°C</title>
            </circle>
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    required: true
  }
})

const viewBoxWidth = 1000
const viewBoxHeight = 150

// Optimal fridge temperature range (USDA recommendation)
const OPTIMAL_TEMP_MIN = 1
const OPTIMAL_TEMP_MAX = 4

// Calculate min and max temperature for scaling
const minTemp = computed(() => {
  if (props.data.length === 0) return 0
  return Math.floor(Math.min(...props.data.map(d => d.temperature)) - 1)
})

const maxTemp = computed(() => {
  if (props.data.length === 0) return 10
  return Math.ceil(Math.max(...props.data.map(d => d.temperature)) + 1)
})

const tempRange = computed(() => maxTemp.value - minTemp.value)

// Convert temperature data to SVG coordinates
const temperatureData = computed(() => {
  if (props.data.length === 0) return []
  
  return props.data.map((entry, index) => {
    const x = (index / (props.data.length - 1)) * viewBoxWidth
    const normalizedTemp = (entry.temperature - minTemp.value) / tempRange.value
    const y = viewBoxHeight - (normalizedTemp * viewBoxHeight)
    
    return {
      x,
      y,
      value: entry.temperature,
      label: formatTime(entry.timestamp)
    }
  })
})

// Create polyline points string
const temperaturePoints = computed(() => {
  return temperatureData.value.map(point => `${point.x},${point.y}`).join(' ')
})

// SVG rect for the optimal temperature band
const optimalBand = computed(() => {
  const clampedMax = Math.min(OPTIMAL_TEMP_MAX, maxTemp.value)
  const clampedMin = Math.max(OPTIMAL_TEMP_MIN, minTemp.value)
  if (clampedMin >= clampedMax) return { y: 0, height: 0 }
  const yTop    = viewBoxHeight - ((clampedMax - minTemp.value) / tempRange.value) * viewBoxHeight
  const yBottom = viewBoxHeight - ((clampedMin - minTemp.value) / tempRange.value) * viewBoxHeight
  return {
    y:      Math.max(0, yTop),
    height: Math.max(0, Math.min(viewBoxHeight, yBottom) - Math.max(0, yTop))
  }
})

const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  const hours = date.getHours()
  const minutes = date.getMinutes().toString().padStart(2, '0')
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const displayHours = hours % 12 || 12
  return `${displayHours}:${minutes} ${ampm}`
}
</script>

<style scoped>
.temperature-chart {
  width: 100%;
  margin-top: 0.75rem;
}

.no-data {
  text-align: center;
  padding: 1rem;
  color: oklch(0.5 0 0);
  font-size: 0.85rem;
  font-style: italic;
  background-color: oklch(0.15 0 0);
  border-radius: 6px;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-container {
  display: flex;
  flex-direction: column;
}

.chart-area {
  display: flex;
  gap: 0.5rem;
  background-color: oklch(0.15 0 0);
  border-radius: 6px;
  padding: 0.75rem;
  min-height: 120px;
}

.y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  padding-right: 0.5rem;
  min-width: 45px;
}

.y-label {
  font-size: 0.7rem;
  color: oklch(0.65 0 0);
}

.chart-content {
  flex: 1;
  position: relative;
}

svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.temp-line {
  filter: drop-shadow(0 0 4px rgba(255, 107, 53, 0.6));
}

.data-point {
  transition: r 0.2s;
  cursor: pointer;
}

.data-point:hover {
  r: 6;
  filter: drop-shadow(0 0 6px rgba(255, 107, 53, 0.8));
}
</style>
