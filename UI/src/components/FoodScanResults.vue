<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { apiUrl } from '../utils/apiBase'

const props = defineProps({
  predictedClass: String,
  confidence: Number,
  top5: Array,
  predictionSource: String,
  geminiError: String,
  category: String,
  packagingType: String,
  storageLocation: String,
  expirationDate: String,
  timeInFridgeHours: {
    type: Number,
    default: 0
  },
  timeOutsideFridgeHours: {
    type: Number,
    default: 0
  },
  notes: String,
  imageBlob: Object,   // Blob from the camera capture, available for in-session scans
  localResult: Object  // Local ResNet18 result returned alongside the Gemini batch prediction
})

const isComparing   = ref(false)
const compareResult = ref(null)
const compareError  = ref(null)

const GENERIC_GEMINI_UNAVAILABLE = 'Gemini is offline or took too long.'

// Build the comparison panel immediately from the batch-time local result,
// so no extra button click / second Gemini call is needed.
const buildCompareFromProps = () => {
  if (!props.localResult) return
  const geminiUnavailable = props.predictionSource !== 'gemini'
  const geminiSide = geminiUnavailable
    ? { error: GENERIC_GEMINI_UNAVAILABLE }
    : {
        predicted_class: props.predictedClass,
        confidence: props.confidence,
        top5: props.top5 ?? []
      }

  const l = (props.localResult.predicted_class ?? '').toLowerCase()
  const g = (props.predictedClass ?? '').toLowerCase()
  const agree = !geminiUnavailable && !!(l && g && (l.includes(g) || g.includes(l) || l === g))
  compareResult.value = {
    local:     props.localResult,
    gemini:    geminiSide,
    agreement: agree
  }
}

const compareVerdictText = computed(() => {
  if (!compareResult.value) return ''
  if (compareResult.value.gemini?.error) return '⚠ Gemini unavailable'
  return compareResult.value.agreement ? '✓ Models agree' : '✗ Models disagree'
})

const compareVerdictClass = computed(() => {
  if (!compareResult.value) return 'verdict-disagree'
  if (compareResult.value.gemini?.error) return 'verdict-unavailable'
  return compareResult.value.agreement ? 'verdict-agree' : 'verdict-disagree'
})

const runComparison = async () => {
  if (!props.imageBlob || isComparing.value) return
  isComparing.value  = true
  compareResult.value = null
  compareError.value  = null
  try {
    const formData = new FormData()
    formData.append('image', props.imageBlob, 'scan.jpg')
    const response = await fetch(apiUrl('/api/classify-food/compare'), {
      method: 'POST',
      body: formData
    })
    if (!response.ok) throw new Error(`Server error ${response.status}`)
    const result = await response.json()
    if (result?.gemini?.error) {
      result.gemini.error = GENERIC_GEMINI_UNAVAILABLE
    }
    compareResult.value = result
  } catch (err) {
    compareError.value = err.message
  } finally {
    isComparing.value = false
  }
}

const emit = defineEmits(['close', 'confirm', 'remove'])

const foodName = ref('')
const foodCategory = ref('other')
const packagingType = ref('sealed')
const storageLocation = ref('regular')
const expirationDate = ref('')
const timeInFridgeHours = ref(0)
const timeOutsideFridgeHours = ref(0)
const selectedPrediction = ref(props.predictedClass)
const selectedConfidence = ref(props.confidence)

const categories = [
  { value: 'dairy', label: 'Dairy' },
  { value: 'produce', label: 'Produce' },
  { value: 'meat', label: 'Meat' },
  { value: 'seafood', label: 'Seafood' },
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
  buildCompareFromProps()

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

  timeInFridgeHours.value = Number.isFinite(props.timeInFridgeHours)
    ? Math.max(0, props.timeInFridgeHours)
    : 0
  timeOutsideFridgeHours.value = Number.isFinite(props.timeOutsideFridgeHours)
    ? Math.max(0, props.timeOutsideFridgeHours)
    : 0
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

watch(() => props.timeInFridgeHours, (newVal) => {
  timeInFridgeHours.value = Number.isFinite(newVal) ? Math.max(0, newVal) : 0
})

watch(() => props.timeOutsideFridgeHours, (newVal) => {
  timeOutsideFridgeHours.value = Number.isFinite(newVal) ? Math.max(0, newVal) : 0
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
    timeInFridgeHours: Math.max(0, Number(timeInFridgeHours.value) || 0),
    timeOutsideFridgeHours: Math.max(0, Number(timeOutsideFridgeHours.value) || 0),
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

        <!-- Model Comparison -->
        <!-- Auto-shown for fresh scans (localResult prop); button is fallback for older items -->
        <div v-if="imageBlob || compareResult" class="compare-section">
          <button
            v-if="imageBlob && !compareResult"
            class="compare-trigger-btn"
            :disabled="isComparing"
            @click="runComparison"
          >
            <span v-if="isComparing">⏳ Running comparison…</span>
            <span v-else>🔬 Compare with Local Model</span>
          </button>

          <p v-if="compareError" class="compare-error">{{ compareError }}</p>

          <div v-if="compareResult" class="compare-panel">
            <h4 class="compare-title">Model Comparison</h4>

            <div class="compare-grid">
              <!-- Gemini column -->
              <div class="compare-col" :class="{ 'compare-col-error': compareResult.gemini?.error }">
                <div class="compare-col-header gemini-header">Gemini</div>
                <template v-if="!compareResult.gemini?.error">
                  <div class="compare-top1">{{ compareResult.gemini?.predicted_class ?? predictedClass }}</div>
                  <div class="compare-conf" :style="{ color: confidenceColor }">
                    {{ (compareResult.gemini?.confidence ?? confidence).toFixed(1) }}%
                  </div>
                  <div class="compare-list">
                    <div
                      v-for="p in (compareResult.gemini?.top5 ?? top5 ?? []).slice(0, 5)"
                      :key="p.class"
                      class="compare-row"
                    >
                      <span class="compare-name">{{ p.class }}</span>
                      <span class="compare-pct">{{ typeof p.confidence === 'number' ? p.confidence.toFixed(1) : p.confidence }}%</span>
                    </div>
                  </div>
                </template>
                <p v-else class="compare-unavailable">{{ compareResult.gemini.error }}</p>
              </div>

              <!-- Local model column -->
              <div class="compare-col" :class="{ 'compare-col-error': compareResult.local?.error }">
                <div class="compare-col-header local-header">Local (ResNet18)</div>
                <template v-if="!compareResult.local?.error">
                  <div class="compare-top1">{{ compareResult.local.predicted_class }}</div>
                  <div class="compare-conf">{{ compareResult.local.confidence.toFixed(1) }}%</div>
                  <div class="compare-list">
                    <div
                      v-for="p in (compareResult.local.top5 ?? []).slice(0, 5)"
                      :key="p.class"
                      class="compare-row"
                    >
                      <span class="compare-name">{{ p.class }}</span>
                      <span class="compare-pct">{{ p.confidence.toFixed(1) }}%</span>
                    </div>
                  </div>
                </template>
                <p v-else class="compare-unavailable">{{ compareResult.local.error }}</p>
              </div>
            </div>

            <div class="compare-verdict" :class="compareVerdictClass">
              {{ compareVerdictText }}
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

          <div class="form-row">
            <div class="form-group">
              <label>Time In Fridge (hours)</label>
              <input
                v-model.number="timeInFridgeHours"
                type="number"
                min="0"
                step="0.1"
                class="form-input"
              />
            </div>

            <div class="form-group">
              <label>Time Outside Fridge (hours)</label>
              <input
                v-model.number="timeOutsideFridgeHours"
                type="number"
                min="0"
                step="0.1"
                class="form-input"
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

@media (max-width: 600px) {
  .form-row {
    grid-template-columns: 1fr;
  }
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

/* ── Model comparison ─────────────────────────────────── */
.compare-section {
  margin-top: 20px;
}

.compare-trigger-btn {
  width: 100%;
  padding: 10px 16px;
  background: oklch(0.28 0.05 265);
  border: 1px solid oklch(0.45 0.1 265);
  border-radius: 8px;
  color: oklch(0.85 0.1 265);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.compare-trigger-btn:hover:not(:disabled) {
  background: oklch(0.33 0.08 265);
  border-color: oklch(0.55 0.15 265);
}

.compare-trigger-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.compare-error {
  color: oklch(0.7 0.2 25);
  font-size: 0.85rem;
  margin: 8px 0 0;
}

.compare-panel {
  margin-top: 16px;
  background: oklch(0.22 0.02 250);
  border: 1px solid oklch(0.32 0.04 265);
  border-radius: 12px;
  padding: 16px;
}

.compare-title {
  color: oklch(0.8 0.02 250);
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 14px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

@media (max-width: 600px) {
  .compare-grid {
    grid-template-columns: 1fr;
  }
}

.compare-col {
  background: oklch(0.25 0.02 250);
  border-radius: 8px;
  padding: 12px;
}

.compare-col-error {
  opacity: 0.7;
}

.compare-col-header {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
}

.gemini-header {
  background: oklch(0.3 0.1 265);
  color: oklch(0.8 0.15 265);
}

.local-header {
  background: oklch(0.3 0.08 145);
  color: oklch(0.8 0.15 145);
}

.compare-top1 {
  font-size: 1rem;
  font-weight: 700;
  color: oklch(0.95 0.02 250);
  text-transform: capitalize;
  margin: 6px 0 2px;
}

.compare-conf {
  font-size: 0.85rem;
  font-weight: 600;
  color: oklch(0.7 0.12 145);
  margin-bottom: 10px;
}

.compare-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.compare-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  padding: 3px 0;
  border-bottom: 1px solid oklch(0.3 0.01 250);
}

.compare-name {
  color: oklch(0.8 0.01 250);
  text-transform: capitalize;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 75%;
}

.compare-pct {
  color: oklch(0.65 0.05 250);
  font-weight: 600;
  flex-shrink: 0;
}

.compare-unavailable {
  color: oklch(0.6 0.1 25);
  font-size: 0.8rem;
  margin: 8px 0 0;
}

.compare-verdict {
  margin-top: 12px;
  text-align: center;
  font-size: 0.9rem;
  font-weight: 700;
  padding: 8px 12px;
  border-radius: 8px;
}

.verdict-agree {
  background: oklch(0.25 0.06 145);
  color: oklch(0.75 0.18 145);
  border: 1px solid oklch(0.4 0.1 145);
}

.verdict-disagree {
  background: oklch(0.25 0.06 25);
  color: oklch(0.75 0.18 25);
  border: 1px solid oklch(0.4 0.1 25);
}

.verdict-unavailable {
  background: oklch(0.25 0.05 85);
  color: oklch(0.82 0.14 85);
  border: 1px solid oklch(0.45 0.1 85);
}
</style>
