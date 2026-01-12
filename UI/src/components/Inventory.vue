<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { loadFoodsFromCSV } from '../utils/csvParser'

defineProps({
  msg: String,
})

const count = ref(0)
const sortBy = ref('freshnessScore') // Default sort by freshness score
const filterBy = ref('all') // Default filter shows all items
const selectedCard = ref(null)
const showPopup = ref(false)
const cards = ref([])

// Available food groups for filtering
const foodGroups = [
  { value: 'all', label: 'All Items' },
  { value: 'dairy', label: 'Dairy' },
  { value: 'produce', label: 'Produce' },
  { value: 'meat', label: 'Meat' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'condiment', label: 'Condiment' },
  { value: 'prepared', label: 'Prepared' },
]

// Function to parse time in fridge string to days
const parseTimeInFridge = (timeString) => {
  const match = timeString.match(/(\d+)/)
  return match ? parseInt(match[1]) : 0
}

// Computed property for filtered and sorted cards
const sortedCards = computed(() => {
  let filteredCards = [...cards.value]
  
  // Apply filter
  if (filterBy.value !== 'all') {
    filteredCards = filteredCards.filter(card => card.foodGroup === filterBy.value)
  }
  
  // Apply sorting
  return filteredCards.sort((a, b) => {
    switch (sortBy.value) {
      case 'freshnessScore':
        return a.freshnessScore - b.freshnessScore
      case 'daysUntilSpoilage':
        return a.daysUntilSpoilage - b.daysUntilSpoilage
      case 'timeInFridge':
        return parseTimeInFridge(a.timeInFridge) - parseTimeInFridge(b.timeInFridge)
      default:
        return 0
    }
  })
})

const handleCardClick = (cardId) => {
  selectedCard.value = cards.value.find(card => card.id === cardId)
  showPopup.value = true
}

const closePopup = () => {
  showPopup.value = false
  selectedCard.value = null
}

const handleKeyDown = (event) => {
  if (event.key === 'Escape') {
    showPopup.value = false
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
  if (score >= 16 && score <= 39) return '#FF6B6B' // Light red
  if (score >= 40 && score <= 59) return '#FFD700' // Yellow
  if (score >= 60 && score <= 84) return '#ADFF2F' // Yellow-green (lighter and more yellow)
  if (score >= 85) return '#228B22' // Forest green (lighter than dark green)
  return '#D3D3D3' // Default gray
}
</script>

<template>
  <div>
    <div class="controls-container">
      <div class="filter-controls">
        <h2>Filter by:</h2>
        <select v-model="filterBy">
          <option v-for="group in foodGroups" :key="group.value" :value="group.value">
            {{ group.label }}
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
      </div>
    </div>

    <div class="cards-grid">
      <div 
        v-for="card in sortedCards" 
        :key="card.id"
        class="card-item"
        :style="{ borderColor: getFreshnessColor(card.freshnessScore) }"
        @click="handleCardClick(card.id)"
      >
        <div class="card-header">
          <h3>{{ card.title }}</h3>
          <span class="freshness-score" :style="{ color: getFreshnessColor(card.freshnessScore) }">{{ card.freshnessScore }}</span>
        </div>
        <p>Estimated days until spoilage: {{ card.daysUntilSpoilage }}</p>
        <p>Time in fridge: {{ card.timeInFridge }}</p>
      </div>
    </div>

    <!-- Food Details Popup -->
    <div v-if="showPopup" class="popup-overlay" @click="closePopup">
      <div class="popup-content" @click.stop>
        <div class="popup-header">
          <h2>{{ selectedCard?.title }}</h2>
          <button class="close-button" @click="closePopup">&times;</button>
        </div>
        <div class="popup-body" v-if="selectedCard">
          <div class="detail-item">
            <span class="detail-label">Freshness Score:</span>
            <span class="detail-value" :style="{ color: getFreshnessColor(selectedCard.freshnessScore) }">
              {{ selectedCard.freshnessScore }}/100
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Days Until Spoilage:</span>
            <span class="detail-value">{{ selectedCard.daysUntilSpoilage }} days</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Time in Fridge:</span>
            <span class="detail-value">{{ selectedCard.timeInFridge }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Food Group:</span>
            <span class="detail-value">{{ selectedCard.foodGroup.charAt(0).toUpperCase() + selectedCard.foodGroup.slice(1) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Status:</span>
            <span class="detail-value" :style="{ color: getFreshnessColor(selectedCard.freshnessScore) }">
              {{ selectedCard.freshnessScore <= 15 ? 'Poor' : selectedCard.freshnessScore <= 39 ? 'Fair' : selectedCard.freshnessScore <= 59 ? 'Good' : selectedCard.freshnessScore <= 84 ? 'Very Good' : 'Excellent' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  margin-top: 1rem;
  width: 100%;
  max-width: 1200px;
}

.card-item {
  background-color: oklch(0.25 0 0);
  border: 1px solid;
  border-radius: 8px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s ease;
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
}

.controls-container {
  display: flex;
  gap: 2rem;
  margin-bottom: 1rem;
}

.filter-controls {
  display: flex;
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

.sort-controls {
  display: flex;
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
</style>
