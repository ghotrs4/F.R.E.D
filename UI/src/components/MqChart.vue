<template>
  <div ref="chartRootRef" class="mq-chart">
    <div v-if="hasNoData" class="no-data">
      <p>No data available</p>
    </div>
    <div v-else class="chart-container">
      <div class="chart-area">
        <div class="y-axis">
          <span class="y-label">High</span>
          <span class="y-label">Mid</span>
          <span class="y-label">Low</span>
        </div>
        <div class="chart-content">
          <svg
            ref="svgRef"
            :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`"
            preserveAspectRatio="none"
            @pointerdown="handleSvgPointerDown"
          >
            <g v-for="sensor in activeSensors" :key="sensor.id">
              <polyline
                :points="getPoints(sensor.id)"
                fill="none"
                :stroke="sensor.color"
                stroke-width="3"
                stroke-linejoin="round"
                stroke-linecap="round"
                :style="{ filter: `drop-shadow(0 0 4px ${sensor.color}99)` }"
              />
              <polyline
                :points="getPoints(sensor.id)"
                fill="none"
                stroke="transparent"
                stroke-width="16"
                stroke-linejoin="round"
                stroke-linecap="round"
                class="line-hit-target"
                @pointerdown.stop.prevent="selectLine(sensor.id, $event)"
              />
              <circle
                v-for="(point, index) in getSensorPlotPoints(sensor.id)"
                :key="`${sensor.id}-${index}`"
                :cx="point.x"
                :cy="point.y"
                r="8"
                fill="transparent"
                class="hover-target"
              >
                <title>{{ `MQ-${sensor.id}: ${point.value} mV${point.label ? ` at ${point.label}` : ''}` }}</title>
              </circle>
            </g>

            <g v-if="selectedPoint && selectedSensor">
              <line
                :x1="selectedPoint.x"
                :x2="selectedPoint.x"
                y1="0"
                :y2="viewBoxHeight"
                :stroke="selectedSensor.color"
                stroke-width="1"
                stroke-dasharray="4,4"
                opacity="0.5"
              />
              <circle
                :cx="selectedPoint.x"
                :cy="selectedPoint.y"
                r="6"
                :fill="selectedSensor.color"
                class="selection-handle"
                @pointerdown.stop.prevent="startDragging"
              />
              <g :transform="`translate(${tooltipX}, ${tooltipY})`" class="selection-tooltip" pointer-events="none">
                <rect
                  x="0"
                  y="0"
                  :width="tooltipWidth"
                  height="24"
                  rx="4"
                  ry="4"
                  :fill="tooltipBackground"
                  :stroke="tooltipBorder"
                  stroke-width="1"
                />
                <rect
                  x="6"
                  y="6"
                  width="10"
                  height="10"
                  rx="2"
                  ry="2"
                  :fill="selectedSensor.color"
                  fill-opacity="0.95"
                  stroke="oklch(0.98 0 0 / 0.45)"
                  stroke-width="0.8"
                />
                <text x="22" y="16" :fill="tooltipTextColor" font-size="11" font-weight="600">
                  {{ tooltipText }}
                </text>
              </g>
            </g>
            <!-- Shared safe threshold line -->
            <line
              x1="0" :x2="viewBoxWidth"
              :y1="SAFE_LINE_Y"
              :y2="SAFE_LINE_Y"
              stroke="oklch(0.8 0 0)"
              stroke-width="1.5"
              stroke-dasharray="6,4"
              opacity="0.55"
            />
            <!-- Shared high threshold guide -->
            <line
              x1="0" :x2="viewBoxWidth"
              :y1="getSharedHighLineY()"
              :y2="getSharedHighLineY()"
              stroke="oklch(0.7 0 0)"
              stroke-width="1"
              stroke-dasharray="2,5"
              opacity="0.3"
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
        <span
          v-if="props.connected && latestReading && latestReading[`mq${sensor.id}`] != null"
          :class="['status-badge', classifyReading(sensor.id, latestReading[`mq${sensor.id}`])]"
        >{{ classifyReading(sensor.id, latestReading[`mq${sensor.id}`]) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { MQ_SAFE_RANGES, MQ_HIGH_THRESHOLD_OFFSET, classifyMqReading } from '../utils/mqSensorConfig'

const props = defineProps({
  data: {
    type: Array,
    required: true
  },
  connected: {
    type: Boolean,
    default: true
  }
})

const viewBoxWidth = 1000
const viewBoxHeight = 150
const chartRootRef = ref(null)
const svgRef = ref(null)
const selectedSensorId = ref(null)
const selectedPointIndex = ref(null)
const isDragging = ref(false)

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

const sensorPointsById = computed(() => {
  const mapped = {}
  for (const sensor of activeSensors.value) {
    mapped[sensor.id] = buildSensorPlotPoints(sensor.id)
  }
  return mapped
})

const hasNoData = computed(() => props.data.length === 0 || activeSensors.value.length === 0)

const SAFE_RANGES = MQ_SAFE_RANGES
const HIGH_THRESHOLD_OFFSET = MQ_HIGH_THRESHOLD_OFFSET
const SAFE_LINE_Y = viewBoxHeight * (2 / 3)
const HIGH_LINE_Y = viewBoxHeight * (1 / 3)

function classifyReading(sensorId, value) {
  return classifyMqReading(sensorId, value)
}

// Use safe ranges to define the chart scale so all sensors share the same
// safe-threshold line while still preserving each sensor's calibrated values.
function getSensorStats(sensorId) {
  const key = `mq${sensorId}`
  const vals = props.data.map(d => d[key]).filter(v => v != null)
  const safe = SAFE_RANGES[sensorId]
  if (safe) {
    const dataMin = vals.length ? Math.min(...vals) : safe.min
    const dataMax = vals.length ? Math.max(...vals) : safe.max + HIGH_THRESHOLD_OFFSET
    return {
      safeMin: safe.min,
      safeMax: safe.max,
      lowerMin: Math.min(dataMin, safe.min),
      upperMax: Math.max(dataMax, safe.max + HIGH_THRESHOLD_OFFSET)
    }
  }
  if (!vals.length) {
    return { safeMin: 0, safeMax: 1, lowerMin: 0, upperMax: 1 }
  }
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  return { safeMin: min, safeMax: max, lowerMin: min, upperMax: max }
}

const latestReading = computed(() => props.data.length ? props.data[props.data.length - 1] : null)

function getYForValue(sensorId, value) {
  const { safeMax, lowerMin, upperMax } = getSensorStats(sensorId)
  const highThreshold = safeMax + HIGH_THRESHOLD_OFFSET

  if (value <= safeMax) {
    const lowerRange = Math.max(safeMax - lowerMin, 1)
    const norm = (value - lowerMin) / lowerRange
    return viewBoxHeight - norm * (viewBoxHeight - SAFE_LINE_Y)
  }

  if (value <= highThreshold) {
    const elevatedRange = Math.max(highThreshold - safeMax, 1)
    const norm = (value - safeMax) / elevatedRange
    return SAFE_LINE_Y - norm * (SAFE_LINE_Y - HIGH_LINE_Y)
  }

  const upperRange = Math.max(upperMax - highThreshold, 1)
  const norm = (value - highThreshold) / upperRange
  return HIGH_LINE_Y - norm * HIGH_LINE_Y
}

function getThresholdY(sensorId, thresholdValue) {
  return getYForValue(sensorId, thresholdValue)
}

function getSharedHighLineY() {
  return HIGH_LINE_Y
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  const hours = date.getHours()
  const minutes = date.getMinutes().toString().padStart(2, '0')
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const displayHours = hours % 12 || 12
  return `${displayHours}:${minutes} ${ampm}`
}

function buildSensorPlotPoints(sensorId) {
  const key = `mq${sensorId}`
  const pts = []
  props.data.forEach((d, i) => {
    const v = d[key]
    if (v == null) return
    const x = (i / Math.max(props.data.length - 1, 1)) * viewBoxWidth
    const y = getYForValue(sensorId, v)
    pts.push({
      x,
      y,
      value: v,
      label: formatTime(d.timestamp)
    })
  })
  return pts
}

function getSensorPlotPoints(sensorId) {
  return sensorPointsById.value[sensorId] || []
}

function getPoints(sensorId) {
  return getSensorPlotPoints(sensorId)
    .map(point => `${point.x},${point.y}`)
    .join(' ')
}

function getSvgPointX(clientX) {
  if (!svgRef.value) return 0
  const rect = svgRef.value.getBoundingClientRect()
  if (!rect.width) return 0
  const x = ((clientX - rect.left) / rect.width) * viewBoxWidth
  return Math.max(0, Math.min(viewBoxWidth, x))
}

function getNearestPointIndex(points, x) {
  if (!points.length) return null
  let nearestIndex = 0
  let nearestDistance = Number.POSITIVE_INFINITY
  points.forEach((point, idx) => {
    const distance = Math.abs(point.x - x)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestIndex = idx
    }
  })
  return nearestIndex
}

function clearSelection() {
  selectedSensorId.value = null
  selectedPointIndex.value = null
  isDragging.value = false
}

function updateSelectionFromClientX(clientX) {
  if (selectedSensorId.value == null) return
  const points = getSensorPlotPoints(selectedSensorId.value)
  const x = getSvgPointX(clientX)
  const nearest = getNearestPointIndex(points, x)
  if (nearest == null) return
  selectedPointIndex.value = nearest
}

function selectLine(sensorId, event) {
  selectedSensorId.value = sensorId
  const points = getSensorPlotPoints(sensorId)
  if (!points.length) {
    selectedPointIndex.value = null
    return
  }
  const x = getSvgPointX(event.clientX)
  selectedPointIndex.value = getNearestPointIndex(points, x)
}

function handleSvgPointerDown(event) {
  if (selectedSensorId.value == null) return
  updateSelectionFromClientX(event.clientX)
}

function startDragging(event) {
  isDragging.value = true
  updateSelectionFromClientX(event.clientX)
}

function handlePointerMove(event) {
  if (!isDragging.value) return
  updateSelectionFromClientX(event.clientX)
}

function handlePointerUp() {
  isDragging.value = false
}

function handleDocumentPointerDown(event) {
  if (!chartRootRef.value) return
  if (!chartRootRef.value.contains(event.target)) {
    clearSelection()
  }
}

const selectedSensor = computed(() =>
  ALL_SENSORS.find(sensor => sensor.id === selectedSensorId.value) || null
)

const selectedPoint = computed(() => {
  if (selectedSensorId.value == null || selectedPointIndex.value == null) return null
  const points = getSensorPlotPoints(selectedSensorId.value)
  if (!points.length) return null
  const clampedIndex = Math.max(0, Math.min(selectedPointIndex.value, points.length - 1))
  return points[clampedIndex]
})

const tooltipText = computed(() => {
  if (!selectedPoint.value || !selectedSensor.value) return ''
  const timeLabel = selectedPoint.value.label ? ` at ${selectedPoint.value.label}` : ''
  return `MQ-${selectedSensor.value.id}: ${selectedPoint.value.value} mV${timeLabel}`
})

const tooltipBackground = 'oklch(0.2 0 0 / 0.96)'
const tooltipTextColor = 'oklch(0.92 0 0)'
const tooltipBorder = computed(() => {
  if (!selectedSensor.value) return 'oklch(0.45 0 0 / 0.7)'
  return `${selectedSensor.value.color}cc`
})

const tooltipWidth = computed(() => Math.max(138, tooltipText.value.length * 6.1 + 30))

const tooltipX = computed(() => {
  if (!selectedPoint.value) return 0
  const preferredRight = selectedPoint.value.x + 10
  const maxX = viewBoxWidth - tooltipWidth.value - 2
  if (preferredRight <= maxX) return preferredRight
  return Math.max(2, selectedPoint.value.x - tooltipWidth.value - 10)
})

const tooltipY = computed(() => {
  if (!selectedPoint.value) return 0
  const preferredAbove = selectedPoint.value.y - 30
  if (preferredAbove >= 2) return preferredAbove
  return Math.min(viewBoxHeight - 26, selectedPoint.value.y + 10)
})

onMounted(() => {
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp)
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onUnmounted(() => {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})
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

.hover-target {
  cursor: crosshair;
}

.line-hit-target {
  cursor: pointer;
}

.selection-handle {
  cursor: ew-resize;
  filter: drop-shadow(0 0 6px rgba(255, 255, 255, 0.4));
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

.status-badge {
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  letter-spacing: 0.04em;
}

.status-badge.low {
  background: oklch(0.35 0.12 145);
  color: oklch(0.85 0.15 145);
}

.status-badge.elevated {
  background: oklch(0.35 0.12 55);
  color: oklch(0.85 0.18 55);
}

.status-badge.high {
  background: oklch(0.35 0.18 25);
  color: oklch(0.85 0.2 25);
}
</style>
