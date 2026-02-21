<!-- to run: "npm run dev" /> -->
<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { RouterView, RouterLink, useRouter, useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import { SidebarProvider, SidebarTrigger } from './components/ui/sidebar'
import CameraCapture from './components/CameraCapture.vue'
import FoodScanResults from './components/FoodScanResults.vue'
import { loadFoodsFromCSV } from './utils/csvParser'

const router = useRouter()
const route = useRoute()

const showCameraPopup = ref(false)
const showResultsPopup = ref(false)
const showRejectConfirm = ref(false)
const detectedItems = ref([])
const selectedItem = ref(null)
const isClassifying = ref(false)

// Helper function to capitalize food names properly
const capitalizeFoodName = (name) => {
  if (!name) return name
  // Split by spaces and capitalize each word
  return name.split(' ').map(word => 
    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  ).join(' ')
}

// Computed property to check if on inventory page
const isOnInventoryPage = computed(() => route.path === '/inventory')

// Load pending items from database
const loadPendingItems = async () => {
  try {
    const response = await fetch('http://localhost:5000/api/foods/pending')
    if (response.ok) {
      const pendingFoods = await response.json()
      
          // Convert database format to frontend format
      detectedItems.value = pendingFoods.map(food => ({
        id: food.id,
        predicted_class: food.name,
        category: food.foodGroup,
        packaging_type: food.packagingType,
        storage_location: food.storageLocation,
        expiration_date: food.expirationDate,
        time_in_fridge: food.timeInFridge,
        days_until_spoilage: food.daysUntilSpoilage,
        confidence: food.confidence || 95,
        top5: food.top5Predictions || [],
        timestamp: new Date().toLocaleTimeString()
      }))
    }
  } catch (error) {
    console.error('Error loading pending items:', error)
  }
}



const openCameraPopup = () => {
  showCameraPopup.value = true
}

const closeCameraPopup = () => {
  showCameraPopup.value = false
}

const handleFinishScanning = async (items) => {
  showCameraPopup.value = false
  
  if (items.length === 0) {
    alert('No food items were detected. Please try again.')
    return
  }
  
  // Capitalize names for new scanned items
  const newItems = items.map(item => ({
    ...item,
    predicted_class: capitalizeFoodName(item.predicted_class)
  }))
  
  // Save items to database with 'pending' status
  for (const item of newItems) {
    try {
      const payload = {
        name: item.predicted_class,
        foodGroup: item.category,
        packagingType: item.packaging_type,
        storageLocation: item.storage_location,
        expirationDate: item.expiration_date || '',
        status: 'pending',
        confidence: item.confidence,
        top5Predictions: item.top5,
        daysUntilSpoilage: parseInt(item.spoilage_prediction) || 7
      }
      
      const response = await fetch('http://localhost:5000/api/foods', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      
      if (!response.ok) {
        console.error('Failed to save pending item:', item.predicted_class)
      }
    } catch (error) {
      console.error('Error saving pending item:', error)
    }
  }
  
  // Reload all pending items from database (merges existing + new)
  await loadPendingItems()
  
  // Navigate to inventory page to show pending items
  router.push('/inventory')
}

const handleItemSelected = (item) => {
  selectedItem.value = item
  showResultsPopup.value = true
}

const getConfidenceClass = (confidence) => {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.5) return 'medium'
  return 'low'
}

const closeResultsPopup = () => {
  showResultsPopup.value = false
  selectedItem.value = null
}

const handleViewPendingItem = (item) => {
  selectedItem.value = item
  showResultsPopup.value = true
}

const handleConfirm = async (updatedData) => {
  // Find the item in detectedItems array
  const item = detectedItems.value.find(item => item.id === selectedItem.value.id)
  if (item) {
    try {
      // Update in database
      const payload = {
        name: capitalizeFoodName(updatedData.name),
        foodGroup: updatedData.category,
        packagingType: updatedData.packaging,
        storageLocation: updatedData.storage,
        expirationDate: updatedData.expirationDate || '',
        status: 'pending', // Keep as pending until "Add to Inventory" is clicked
        confidence: updatedData.confidence
      }
      
      const response = await fetch(`http://localhost:5000/api/foods/${item.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      
      if (response.ok) {
        // Update the item in local state (preserve confidence and top5)
        // Create new array to trigger Vue reactivity
        let updatedItem = null
        detectedItems.value = detectedItems.value.map(i => {
          if (i.id === item.id) {
            updatedItem = {
              ...i,
              predicted_class: capitalizeFoodName(updatedData.name),
              category: updatedData.category,
              packaging_type: updatedData.packaging,
              storage_location: updatedData.storage,
              expiration_date: updatedData.expirationDate || '',
              confidence: updatedData.confidence
            }
            return updatedItem
          }
          return i
        })
        // Update selectedItem to reference the new object
        if (updatedItem) {
          selectedItem.value = updatedItem
        }
        // Don't reload from database to preserve AI scan data
      } else {
        console.error('Failed to update item')
      }
    } catch (error) {
      console.error('Error updating item:', error)
    }
  }
  
  // Close the results popup
  closeResultsPopup()
}

const handleRemovePendingItem = async () => {
  // Delete the item from database
  if (selectedItem.value) {
    try {
      const response = await fetch(`http://localhost:5000/api/foods/${selectedItem.value.id}`, {
        method: 'DELETE'
      })
      
      if (response.ok) {
        // Reload pending items
        await loadPendingItems()
      } else {
        console.error('Failed to delete item')
      }
    } catch (error) {
      console.error('Error deleting item:', error)
    }
  }
  
  // Close the results popup
  closeResultsPopup()
}

const handleRejectAll = () => {
  showRejectConfirm.value = true
}

const confirmRejectAll = async () => {
  try {
    const response = await fetch('http://localhost:5000/api/foods/pending/delete', {
      method: 'DELETE'
    })
    
    if (response.ok) {
      // Clear local array
      detectedItems.value = []
      showRejectConfirm.value = false
    } else {
      console.error('Failed to delete pending items')
    }
  } catch (error) {
    console.error('Error deleting pending items:', error)
  }
}

const cancelRejectAll = () => {
  showRejectConfirm.value = false
}

const closeItemList = async () => {
  try {
    // Confirm all pending items (change status to 'confirmed')
    const response = await fetch('http://localhost:5000/api/foods/pending/confirm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })
    
    if (response.ok) {
      // Clear local pending items array
      detectedItems.value = []
      alert('All items added to inventory successfully!')
    } else {
      alert('Failed to add items to inventory')
    }
  } catch (error) {
    console.error('Error confirming items:', error)
    alert('Error adding items to inventory')
  }
}

const navigateToInventory = () => {
  router.push('/inventory')
}

const handleKeyDown = (event) => {
  // Escape to close popups (except item list - needs OK button)
  if (event.key === 'Escape') {
    if (showResultsPopup.value) {
      closeResultsPopup()
    } else if (showCameraPopup.value) {
      closeCameraPopup()
    }
    return
  }
  
  // Ctrl+Shift+S to open camera scan
  if (event.ctrlKey && event.shiftKey && event.key === 'S') {
    event.preventDefault()
    openCameraPopup()
  }
}

onMounted(() => {
  loadPendingItems()
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <SidebarProvider class="sidebar-provider">
    <AppSidebar />
    <div class="content-wrapper">
      <SidebarTrigger class="sidebar-trigger" />
      
      <main>
        <!-- Pending Items Banner -->
        <div v-if="detectedItems.length > 0" class="pending-banner">
          <div class="banner-content">
            <div class="banner-info">
              <span class="banner-icon">⚠️</span>
              <span class="banner-text">{{ detectedItems.length }} Item{{ detectedItems.length > 1 ? 's' : '' }} Pending</span>
            </div>
            <div class="banner-actions">
              <button v-if="!isOnInventoryPage" class="banner-button view-button" @click="navigateToInventory">
                View
              </button>
              <template v-else>
                <button class="banner-button reject-button" @click="handleRejectAll">
                  Reject All
                </button>
                <button class="banner-button add-button" @click="closeItemList">
                  Add to Inventory
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <RouterView :pending-items="detectedItems" @view-pending-item="handleViewPendingItem" />
      </main>
      <div class="right-spacer"></div>
    </div>
    
    <!-- Global Camera Popup -->
    <CameraCapture 
      v-if="showCameraPopup"
      @close="closeCameraPopup"
      @finish="handleFinishScanning"
    />
    
    <!-- Global Results Popup -->
    <FoodScanResults
      v-if="showResultsPopup && selectedItem"
      :predicted-class="selectedItem.predicted_class"
      :confidence="selectedItem.confidence"
      :top5="selectedItem.top5"
      :category="selectedItem.category"
      :packaging-type="selectedItem.packaging_type"
      :storage-location="selectedItem.storage_location"
      :expiration-date="selectedItem.expiration_date"
      :notes="selectedItem.notes"
      @close="closeResultsPopup"
      @confirm="handleConfirm"
      @remove="handleRemovePendingItem"
    />
    
    <!-- Reject All Confirmation Popup -->
    <div v-if="showRejectConfirm" class="confirm-overlay" @click="cancelRejectAll">
      <div class="confirm-popup" @click.stop>
        <h3>Reject All Items?</h3>
        <p>Are you sure you want to remove all {{ detectedItems.length }} pending item{{ detectedItems.length > 1 ? 's' : '' }}?</p>
        <p class="warning-text">This action cannot be undone.</p>
        <div class="confirm-buttons">
          <button class="cancel-btn" @click="cancelRejectAll">Cancel</button>
          <button class="reject-btn" @click="confirmRejectAll">Reject All</button>
        </div>
      </div>
    </div>
    
    <!-- Global AI Classification Loading Overlay -->
    <div v-if="isClassifying" class="ai-loading-overlay">
      <div class="ai-loading-content">
        <div class="spinner"></div>
        <p class="loading-text">Identifying item...</p>
      </div>
    </div>
  </SidebarProvider>
</template>

<style scoped>
.sidebar-provider {
  height: 100vh;
  width: 100vw;
  display: flex;
}

.right-spacer {
  width: calc(40px + 2rem);
  flex-shrink: 0;
}

.content-wrapper {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: auto;
  padding-bottom: 2rem;
}

.sidebar-trigger {
  flex-shrink: 0;
  padding: 1rem;
  display: flex;
  align-items: flex-start;
}

main {
  flex: 1;
  max-width: unset;
  margin: 0;
  padding: 0 0 2rem 0;
  text-align: left;
  height: 100%;
  width: 100%;
}

nav {
  position: fixed;
  top: 0;
  left: 0;
  padding: 1rem;
  z-index: 1000;
}

.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: filter 300ms;
}
.logo:hover {
  filter: drop-shadow(0 0 2em #646cffaa);
}
.logo.vue:hover {
  filter: drop-shadow(0 0 2em #42b883aa);
}

.ai-loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.85);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.ai-loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}

.spinner {
  width: 60px;
  height: 60px;
  border: 4px solid oklch(0.3 0 0);
  border-top: 4px solid oklch(0.7 0.15 265);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text {
  margin: 0;
  color: oklch(0.9 0 0);
  font-size: 1.25rem;
  font-weight: 500;
}

/* Pending Items Banner */
.pending-banner {
  width: 100%;
  background: transparent;
  border: 2px solid oklch(0.55 0.2 45);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  margin: 1rem 0;
}

.banner-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 2rem;
  max-width: 100%;
}

.banner-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.banner-icon {
  font-size: 1.25rem;
}

.banner-text {
  color: oklch(0.95 0 0);
  font-size: 1rem;
  font-weight: 600;
}

.banner-actions {
  display: flex;
  gap: 0.5rem;
}

.banner-button {
  padding: 0.5rem 1.25rem;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.view-button {
  background: oklch(0.3 0 0);
  color: oklch(0.95 0 0);
}

.view-button:hover {
  background: oklch(0.35 0 0);
  transform: translateY(-1px);
}

.add-button {
  background: oklch(0.65 0.2 145);
  color: oklch(0.95 0 0);
}

.add-button:hover {
  background: oklch(0.7 0.22 145);
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(0, 255, 100, 0.3);
}

.reject-button {
  background: oklch(0.55 0.2 25);
  color: oklch(0.95 0 0);
}

.reject-button:hover {
  background: oklch(0.6 0.22 25);
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(255, 100, 100, 0.3);
}

/* Confirmation Popup */
.confirm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(4px);
}

.confirm-popup {
  background: oklch(0.15 0 0);
  border: 2px solid oklch(0.3 0 0);
  border-radius: 12px;
  padding: 2rem;
  max-width: 450px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.confirm-popup h3 {
  margin: 0 0 1rem 0;
  font-size: 1.5rem;
  color: oklch(0.55 0.2 25);
}

.confirm-popup p {
  margin: 0.75rem 0;
  color: oklch(0.8 0 0);
  line-height: 1.5;
}

.warning-text {
  font-size: 0.9rem;
  color: oklch(0.6 0.15 35);
  font-style: italic;
}

.confirm-buttons {
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
}

.confirm-buttons button {
  flex: 1;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.cancel-btn {
  background: oklch(0.3 0 0);
  color: oklch(0.95 0 0);
}

.cancel-btn:hover {
  background: oklch(0.35 0 0);
  transform: translateY(-2px);
}

.reject-btn {
  background: oklch(0.55 0.2 25);
  color: oklch(0.95 0 0);
}

.reject-btn:hover {
  background: oklch(0.6 0.22 25);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 100, 100, 0.3);
}

/* Responsive Design */
@media (max-width: 768px) {
  .right-spacer {
    display: none;
  }

  .content-wrapper {
    flex-direction: column;
  }

  .sidebar-trigger {
    padding: 0.75rem;
  }

  main {
    padding: 1rem;
  }
}

@media (max-width: 480px) {
  .sidebar-trigger {
    padding: 0.5rem;
  }

  main {
    padding: 0.75rem;
  }
}
</style>
