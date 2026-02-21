<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  predictedClass: String,
  confidence: Number,
  top5: Array,
  category: String,
  packagingType: String,
  storageLocation: String,
  expirationDate: String,
  notes: String
})

const emit = defineEmits(['close', 'confirm', 'remove'])

const foodName = ref('')
const foodCategory = ref('other')
const packagingType = ref('sealed')
const storageLocation = ref('regular')
const expirationDate = ref('')
const selectedPrediction = ref(props.predictedClass)
const selectedConfidence = ref(props.confidence)

const categories = [
  { value: 'dairy', label: 'Dairy' },
  { value: 'produce', label: 'Produce' },
  { value: 'meat', label: 'Meat' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'condiment', label: 'Condiment' },
  { value: 'prepared', label: 'Prepared' },
  { value: 'other', label: 'Other' }
]

const packagingOptions = [
  { value: 'sealed', label: 'Sealed' },
  { value: 'opened', label: 'Opened' },
  { value: 'loose', label: 'Loose' },
  { value: 'canned', label: 'Canned' },
  { value: 'bottled', label: 'Bottled' },
  { value: 'boxed', label: 'Boxed' },
  { value: 'bagged', label: 'Bagged' },
  { value: 'wrapped', label: 'Wrapped' }
]

const storageOptions = [
  { value: 'regular', label: 'Regular Shelf' },
  { value: 'crisper', label: 'Crisper Drawer' },
  { value: 'door', label: 'Door Shelf' }
]

const confidenceColor = computed(() => {
  if (selectedConfidence.value >= 80) return 'oklch(0.7 0.15 160)'
  if (selectedConfidence.value >= 50) return 'oklch(0.7 0.15 60)'
  return 'oklch(0.7 0.15 30)'
})

const selectPrediction = (predictionName, confidence) => {
  selectedPrediction.value = predictionName
  selectedConfidence.value = confidence
  foodName.value = predictionName
}

// Pre-fill form based on AI-extracted data
onMounted(() => {
  if (props.predictedClass) {
    foodName.value = props.predictedClass
    // Normalize selectedPrediction to match top5 casing so the selected highlight works
    const match = props.top5?.find(p => p.class?.toLowerCase() === props.predictedClass.toLowerCase())
    selectedPrediction.value = match ? match.class : props.predictedClass
  }
  
  // Use AI-extracted category if provided
  if (props.category) {
    foodCategory.value = props.category
  }
  
  // Use AI-extracted packaging type if provided
  if (props.packagingType) {
    packagingType.value = props.packagingType
  }
  
  // Use AI-extracted storage location if provided
  if (props.storageLocation) {
    storageLocation.value = props.storageLocation
  }
  
  // Use AI-extracted expiration date if provided
  if (props.expirationDate) {
    expirationDate.value = props.expirationDate
  }
})

// Watch for prop changes and update form fields
// This ensures form reflects the current state after edits are confirmed
watch(() => props.predictedClass, (newVal) => {
  if (newVal) {
    foodName.value = newVal
    // Match casing to the top5 list entry if possible, so the selected highlight works
    const match = props.top5?.find(p => p.class?.toLowerCase() === newVal.toLowerCase())
    selectedPrediction.value = match ? match.class : newVal
  }
})

watch(() => props.category, (newVal) => {
  if (newVal) {
    foodCategory.value = newVal
  }
})

watch(() => props.packagingType, (newVal) => {
  if (newVal) {
    packagingType.value = newVal
  }
})

watch(() => props.storageLocation, (newVal) => {
  if (newVal) {
    storageLocation.value = newVal
  }
})

watch(() => props.expirationDate, (newVal) => {
  expirationDate.value = newVal || ''
})

watch(() => props.confidence, (newVal) => {
  if (newVal) {
    selectedConfidence.value = newVal
  }
})

const handleKeyDown = (event) => {
  if (event.key === 'Escape') {
    emit('close')
  } else if (event.key === 'Enter') {
    confirmChanges()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})

const confirmChanges = () => {
  emit('confirm', {
    name: foodName.value,
    category: foodCategory.value,
    packaging: packagingType.value,
    storage: storageLocation.value,
    expirationDate: expirationDate.value || null,
    confidence: selectedConfidence.value
  })
}

const removeItem = () => {
  emit('remove')
}
</script>

<template>
  <div class="results-popup-overlay" @click="$emit('close')">
    <div class="results-popup-content" @click.stop>
      <div class="results-header">
        <h2>Scan Results</h2>
        <button class="close-button" @click="$emit('close')">&times;</button>
      </div>
      
      <div class="results-body">
        <!-- Classification Results -->
        <div class="prediction-section">
          <div class="main-prediction">
            <h3>Predicted Food</h3>
            <p class="predicted-name">{{ selectedPrediction }}</p>
            <p class="confidence" :style="{ color: confidenceColor }">
              Confidence: {{ selectedConfidence.toFixed(1) }}%
            </p>
          </div>
          
          <div v-if="top5 && top5.length > 0" class="top5-section">
            <h4>All Predictions (click to select):</h4>
            <div class="top5-list">
              <div 
                v-for="(pred, index) in top5" 
                :key="index"
                class="top5-item"
                :class="{ 'selected': selectedPrediction?.toLowerCase() === pred.class?.toLowerCase() }"
                @click="selectPrediction(pred.class, pred.confidence)"
              >
                <span class="top5-name">{{ pred.class }}</span>
                <span v-if="selectedPrediction?.toLowerCase() !== pred.class?.toLowerCase()" class="top5-confidence">{{ pred.confidence.toFixed(1) }}%</span>
                <span v-if="selectedPrediction?.toLowerCase() === pred.class?.toLowerCase()" class="selected-indicator">✓</span>
              </div>
            </div>
          </div>
        </div>
        
        <div class="divider"></div>
        
        <!-- Food Details Form -->
        <div class="form-section">
          <h3>Food Details</h3>
          <p class="form-hint">Review and modify the details below before saving</p>
          
          <div class="form-group">
            <label>Food Name</label>
            <input 
              v-model="foodName" 
              type="text" 
              placeholder="Enter food name"
              class="form-input"
            />
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Category</label>
              <select v-model="foodCategory" class="form-select">
                <option v-for="cat in categories" :key="cat.value" :value="cat.value">
                  {{ cat.label }}
                </option>
              </select>
            </div>
            
            <div class="form-group">
              <label>Packaging</label>
              <select v-model="packagingType" class="form-select">
                <option v-for="pkg in packagingOptions" :key="pkg.value" :value="pkg.value">
                  {{ pkg.label }}
                </option>
              </select>
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>Storage Location</label>
              <select v-model="storageLocation" class="form-select">
                <option v-for="loc in storageOptions" :key="loc.value" :value="loc.value">
                  {{ loc.label }}
                </option>
              </select>
            </div>
            
            <div class="form-group">
              <label>Expiration Date (Optional)</label>
              <input 
                v-model="expirationDate" 
                type="date" 
                class="form-input"
                id="date"
              />
            </div>
          </div>
          
          <div class="button-group">
            <button class="remove-button" @click="removeItem">
              🗑️ Remove Item
            </button>
            <button class="confirm-button" @click="confirmChanges">
              ✓ Confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.results-popup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.results-popup-content {
  background: oklch(0.2 0.02 250);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 32px;
  border-bottom: 1px solid oklch(0.3 0.02 250);
}

.results-header h2 {
  color: oklch(0.9 0.02 250);
  font-size: 1.8rem;
  font-weight: 600;
  margin: 0;
}

.close-button {
  background: none;
  border: none;
  color: oklch(0.7 0.02 250);
  font-size: 2rem;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  transition: all 0.2s;
}

.close-button:hover {
  background: oklch(0.3 0.02 250);
  color: oklch(0.95 0.02 250);
}

.results-body {
  padding: 32px;
}

.prediction-section {
  margin-bottom: 32px;
}

.main-prediction {
  text-align: center;
  margin-bottom: 24px;
}

.main-prediction h3 {
  color: oklch(0.8 0.02 250);
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0 0 12px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.predicted-name {
  font-size: 2rem;
  font-weight: 700;
  color: oklch(0.95 0.02 250);
  margin: 0 0 8px 0;
  text-transform: capitalize;
}

.confidence {
  font-size: 1.2rem;
  font-weight: 600;
  margin: 0;
}

.top5-section {
  background: oklch(0.25 0.02 250);
  border-radius: 12px;
  padding: 20px;
}

.top5-section h4 {
  color: oklch(0.8 0.02 250);
  font-size: 0.9rem;
  font-weight: 600;
  margin: 0 0 16px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.top5-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.top5-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: oklch(0.22 0.02 250);
  border-radius: 8px;
  transition: all 0.2s;
  cursor: pointer;
  position: relative;
}

.top5-item:hover {
  background: oklch(0.27 0.02 250);
  transform: translateX(4px);
}

.top5-item.selected {
  background: oklch(0.3 0.1 250);
  border: 2px solid oklch(0.6 0.15 265);
  padding: 10px 14px;
}

.selected-indicator {
  color: oklch(0.7 0.2 145);
  font-size: 1.2rem;
  font-weight: bold;
  margin-left: 8px;
}

.top5-name {
  color: oklch(0.9 0.02 250);
  font-weight: 500;
  text-transform: capitalize;
}

.top5-confidence {
  color: oklch(0.7 0.02 250);
  font-weight: 600;
  font-size: 0.9rem;
}

.divider {
  height: 1px;
  background: oklch(0.3 0.02 250);
  margin: 32px 0;
}

.form-section h3 {
  color: oklch(0.9 0.02 250);
  font-size: 1.3rem;
  font-weight: 600;
  margin: 0 0 8px 0;
}

.form-hint {
  color: oklch(0.6 0.02 250);
  font-size: 0.9rem;
  margin: 0 0 20px 0;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  color: oklch(0.8 0.02 250);
  font-size: 0.9rem;
  font-weight: 600;
  margin-bottom: 8px;
}

.form-input,
.form-select {
  width: 100%;
  padding: 12px 16px;
  background: oklch(0.25 0.02 250);
  border: 1px solid oklch(0.35 0.02 250);
  border-radius: 8px;
  color: oklch(0.9 0.02 250);
  font-size: 1rem;
  transition: all 0.2s;
  text-transform: capitalize;
}

#date {
    text-transform: none;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: oklch(0.7 0.15 250);
  background: oklch(0.27 0.02 250);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.button-group {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin-top: 32px;
}

.confirm-button {
  flex: 1;
  max-width: 250px;
  padding: 14px 24px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  background: oklch(0.65 0.2 145);
  color: oklch(0.95 0 0);
}

.confirm-button:hover {
  background: oklch(0.7 0.22 145);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 255, 100, 0.3);
}

.remove-button {
  flex: 1;
  max-width: 250px;
  padding: 14px 24px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  background: oklch(0.55 0.2 25);
  color: oklch(0.95 0 0);
}

.remove-button:hover {
  background: oklch(0.6 0.22 25);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 100, 100, 0.3);
}
</style>
