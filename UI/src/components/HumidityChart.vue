<template>
  <div class="humidity-chart">
    <div v-if="data.length === 0" class="no-data">
      <p>No data available</p>
    </div>
    <div v-else class="chart-container">
      <div class="chart-area">
        <div class="y-axis">
          <span class="y-label">{{ maxHumidity.toFixed(0) }}%</span>
          <span class="y-label">{{ ((maxHumidity + minHumidity) / 2).toFixed(0) }}%</span>
          <span class="y-label">{{ minHumidity.toFixed(0) }}%</span>
        </div>
        <div class="chart-content">
          <svg :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`" preserveAspectRatio="none">
            <!-- Humidity line -->
            <polyline
              :points="humidityPoints"
              fill="none"
              stroke="#4A90E2"
              stroke-width="3"
              class="humidity-line"
            />
            <!-- Humidity points -->
            <circle
              v-for="(point, index) in humidityData"
              :key="`humidity-${index}`"
              :cx="point.x"
              :cy="point.y"
              r="4"
              fill="#4A90E2"
              class="data-point"
            >
              <title>{{ point.label }}: {{ point.value.toFixed(1) }}%</title>
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

// Calculate min and max humidity for scaling
const minHumidity = computed(() => {
  if (props.data.length === 0) return 0
  return Math.floor(Math.min(...props.data.map(d => d.humidity)) - 5)
})

const maxHumidity = computed(() => {
  if (props.data.length === 0) return 100
  return Math.ceil(Math.max(...props.data.map(d => d.humidity)) + 5)
})

const humidityRange = computed(() => maxHumidity.value - minHumidity.value)

// Convert humidity data to SVG coordinates
const humidityData = computed(() => {
  if (props.data.length === 0) return []
  
  return props.data.map((entry, index) => {
    const x = (index / (props.data.length - 1)) * viewBoxWidth
    const normalizedHumidity = (entry.humidity - minHumidity.value) / humidityRange.value
    const y = viewBoxHeight - (normalizedHumidity * viewBoxHeight)
    
    return {
      x,
      y,
      value: entry.humidity,
      label: formatTime(entry.timestamp)
    }
  })
})

// Create polyline points string
const humidityPoints = computed(() => {
  return humidityData.value.map(point => `${point.x},${point.y}`).join(' ')
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
.humidity-chart {
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
  min-width: 40px;
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

.humidity-line {
  filter: drop-shadow(0 0 4px rgba(74, 144, 226, 0.6));
}

.data-point {
  transition: r 0.2s;
  cursor: pointer;
}

.data-point:hover {
  r: 6;
  filter: drop-shadow(0 0 6px rgba(74, 144, 226, 0.8));
}
</style>
