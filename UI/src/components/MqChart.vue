<template>
  <div class="mq-chart">
    <div v-if="hasNoData" class="no-data">
      <p>No data available</p>
    </div>
    <div v-else class="chart-container">
      <div class="chart-area">
        <div class="y-axis">
          <span class="y-label">{{ maxVal }}</span>
          <span class="y-label">{{ Math.round((maxVal + minVal) / 2) }}</span>
          <span class="y-label">{{ minVal }}</span>
        </div>
        <div class="chart-content">
          <svg :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`" preserveAspectRatio="none">
            <polyline
              v-for="sensor in activeSensors"
              :key="sensor.id"
              :points="getPoints(sensor.id)"
              fill="none"
              :stroke="sensor.color"
              stroke-width="3"
              stroke-linejoin="round"
              stroke-linecap="round"
              :style="{ filter: `drop-shadow(0 0 4px ${sensor.color}99)` }"
            />
          </svg>
        </div>
      </div>
    </div>

    <!-- Legend always visible -->
    <div class="mq-legend">
      <div v-for="sensor in ALL_SENSORS" :key="sensor.id" class="legend-item">
        <span class="legend-swatch" :style="{ background: sensor.color }"></span>
        <span class="legend-label">MQ-{{ sensor.id }}: {{ sensor.name }}</span>
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

// All known MQ sensors with display names and colours
const ALL_SENSORS = [
  { id: 2,   name: 'Methane',        color: '#FF6B35' },
  { id: 3,   name: 'Ethanol',  color: '#A855F7' },
  { id: 4,   name: 'Methane',            color: '#3B82F6' },
  { id: 5,   name: 'Natural Gas',  color: '#22C55E' },
  { id: 8,   name: 'Hydrogen',           color: '#06B6D4' },
  { id: 9,   name: 'Carbon Monoxide / Methane',    color: '#EF4444' },
  { id: 135, name: 'Air Quality',        color: '#EAB308' },
]

// Only show sensors that have at least one reading in the data
const activeSensors = computed(() => {
  return ALL_SENSORS.filter(s =>
    props.data.some(d => d[`mq${s.id}`] != null)
  )
})

const hasNoData = computed(() => props.data.length === 0 || activeSensors.value.length === 0)

// Global min/max across all active sensors for consistent Y axis
const allValues = computed(() => {
  const vals = []
  for (const s of activeSensors.value) {
    for (const d of props.data) {
      const v = d[`mq${s.id}`]
      if (v != null) vals.push(v)
    }
  }
  return vals
})

const minVal = computed(() => allValues.value.length ? Math.floor(Math.min(...allValues.value)) : 0)
const maxVal = computed(() => allValues.value.length ? Math.ceil(Math.max(...allValues.value))  : 1000)
const valRange = computed(() => Math.max(maxVal.value - minVal.value, 1))

function getPoints(sensorId) {
  const key = `mq${sensorId}`
  const pts = []
  props.data.forEach((d, i) => {
    const v = d[key]
    if (v == null) return
    const x = (i / Math.max(props.data.length - 1, 1)) * viewBoxWidth
    const norm = (v - minVal.value) / valRange.value
    const y = viewBoxHeight - norm * viewBoxHeight
    pts.push(`${x},${y}`)
  })
  return pts.join(' ')
}
</script>

<style scoped>
.mq-chart {
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

/* Legend */
.mq-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  padding-top: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.legend-swatch {
  width: 20px;
  height: 3px;
  border-radius: 2px;
  flex-shrink: 0;
}

.legend-label {
  font-size: 0.7rem;
  color: oklch(0.65 0 0);
}
</style>
