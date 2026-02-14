<template>
  <div class="history-chart">
    <h3>{{ title }}</h3>
    <div v-if="data.length === 0" class="no-data">
      <p>No historical data yet. Start tracking items to see trends!</p>
    </div>
    <div v-else class="chart-container">
      <div class="chart-bars">
        <div v-for="(entry, index) in displayData" :key="index" class="bar-group">
          <div class="bars">
            <div 
              v-if="entry.itemsConsumed > 0"
              class="bar consumed" 
              :style="{ height: `${(entry.itemsConsumed / maxValue) * 100}%` }"
              :title="`Consumed: ${entry.itemsConsumed}`"
            ></div>
            <div 
              v-if="entry.itemsWasted > 0"
              class="bar wasted" 
              :style="{ height: `${(entry.itemsWasted / maxValue) * 100}%` }"
              :title="`Wasted: ${entry.itemsWasted}`"
            ></div>
          </div>
          <div class="bar-label">{{ formatDate(entry.date) }}</div>
        </div>
      </div>
      <div class="legend">
        <div class="legend-item">
          <span class="legend-color consumed"></span>
          <span>Consumed</span>
        </div>
        <div class="legend-item">
          <span class="legend-color wasted"></span>
          <span>Wasted</span>
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
  },
  title: {
    type: String,
    default: 'Waste History'
  }
})

const displayData = computed(() => {
  // Show last 7 days
  return props.data.slice(-7)
})

const maxValue = computed(() => {
  if (displayData.value.length === 0) return 1
  return Math.max(...displayData.value.map(entry => 
    entry.itemsConsumed + entry.itemsWasted
  ))
})

const formatDate = (dateStr) => {
  const date = new Date(dateStr)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[date.getMonth()]} ${date.getDate()}`
}
</script>

<style scoped>
.history-chart {
  width: 100%;
}

.history-chart h3 {
  margin: 0 0 1rem 0;
  color: oklch(0.85 0 0);
  font-size: 1.1rem;
}

.no-data {
  text-align: center;
  padding: 2rem;
  color: oklch(0.6 0 0);
  font-style: italic;
}

.chart-container {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.chart-bars {
  display: flex;
  justify-content: space-around;
  align-items: flex-end;
  height: 200px;
  padding: 1rem;
  background-color: oklch(0.15 0 0);
  border-radius: 8px;
  gap: 0.5rem;
}

.bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.bars {
  display: flex;
  gap: 2px;
  align-items: flex-end;
  height: 100%;
  justify-content: center;
}

.bar {
  width: 12px;
  border-radius: 4px 4px 0 0;
  transition: all 0.3s;
  min-height: 4px;
}

.bar:hover {
  opacity: 0.8;
  transform: scaleY(1.05);
}

.bar.consumed {
  background-color: #00FF00;
  box-shadow: 0 0 8px rgba(0, 255, 0, 0.5);
}

.bar.wasted {
  background-color: #FF0000;
  box-shadow: 0 0 8px rgba(255, 0, 0, 0.5);
}

.bar-label {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: oklch(0.7 0 0);
  text-align: center;
}

.legend {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: oklch(0.8 0 0);
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 4px;
}

.legend-color.consumed {
  background-color: #00FF00;
}

.legend-color.wasted {
  background-color: #FF0000;
}
</style>
