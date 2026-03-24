<!-- to run: "npm run dev" /> -->
<script setup>
import { ref, watch, computed, shallowRef, nextTick, onMounted, onUnmounted } from 'vue'
import { RouterView, RouterLink, useRouter, useRoute } from 'vue-router'
import lottie from 'lottie-web'
import AppSidebar from './components/AppSidebar.vue'
import { SidebarProvider, SidebarTrigger } from './components/ui/sidebar'
import CameraCapture from './components/CameraCapture.vue'
import FoodScanResults from './components/FoodScanResults.vue'
import appLogo from './assets/fred.svg'
import fredThinkAnimation from './assets/fred_think.json'
import { loadFoodsFromCSV } from './utils/csvParser'
import { apiUrl } from './utils/apiBase'

const router = useRouter()
const route = useRoute()

const showCameraPopup = ref(false)
const showResultsPopup = ref(false)
const showRejectConfirm = ref(false)
const detectedItems = ref([])
const selectedItem = ref(null)
const isClassifying = ref(false)
const classifyingCount = ref(0)
const isFullscreen = ref(false)
const shouldRestoreFullscreen = ref(false)
const geminiEnabled = ref(true)
const classificationAnimRef = ref(null)
const classificationAnimInstance = shallowRef(null)
const imageBlobCache = ref({})    // food name (lowercase) -> Blob, for in-session compare
const localResultCache = ref({})  // food name (lowercase) -> local model result, for in-session compare
const outgoingItems = ref([])

const FULLSCREEN_PREF_KEY = 'fred_fullscreen_enabled'
const GEMINI_ENABLED_PREF_KEY = 'fred_gemini_enabled'

const persistFullscreenPreference = (enabled) => {
  try {
    localStorage.setItem(FULLSCREEN_PREF_KEY, enabled ? 'true' : 'false')
  } catch {}
}

const loadFullscreenPreference = () => {
  try {
    return localStorage.getItem(FULLSCREEN_PREF_KEY) === 'true'
  } catch {
    return false
  }
}

const loadGeminiPreference = () => {
  try {
    const stored = localStorage.getItem(GEMINI_ENABLED_PREF_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

const setGeminiEnabled = (enabled) => {
  geminiEnabled.value = Boolean(enabled)
  try {
    localStorage.setItem(GEMINI_ENABLED_PREF_KEY, geminiEnabled.value ? 'true' : 'false')
  } catch {}
}

const syncFullscreenState = () => {
  isFullscreen.value = Boolean(document.fullscreenElement)
  persistFullscreenPreference(isFullscreen.value)
}

const removeFullscreenRestoreListeners = () => {
  document.removeEventListener('pointerdown', requestFullscreenIfPreferred, true)
  document.removeEventListener('keydown', requestFullscreenIfPreferred, true)
  document.removeEventListener('touchstart', requestFullscreenIfPreferred, true)
}

async function requestFullscreenIfPreferred() {
  if (!shouldRestoreFullscreen.value || document.fullscreenElement) {
    removeFullscreenRestoreListeners()
    return
  }

  try {
    await document.documentElement.requestFullscreen()
    shouldRestoreFullscreen.value = false
    removeFullscreenRestoreListeners()
  } catch (error) {
    console.error('Fullscreen restore failed:', error)
  }
}

const addFullscreenRestoreListeners = () => {
  document.addEventListener('pointerdown', requestFullscreenIfPreferred, true)
  document.addEventListener('keydown', requestFullscreenIfPreferred, true)
  document.addEventListener('touchstart', requestFullscreenIfPreferred, true)
}

const toggleFullscreen = async () => {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen()
      shouldRestoreFullscreen.value = false
    } else {
      await document.exitFullscreen()
      shouldRestoreFullscreen.value = false
    }
  } catch (error) {
    console.error('Fullscreen toggle failed:', error)
  }
}

const handleClassifying = (value) => {
  isClassifying.value = Boolean(value)
  classifyingCount.value = Number(value) || 0
}

const destroyClassificationAnimation = () => {
  if (classificationAnimInstance.value) {
    classificationAnimInstance.value.destroy()
    classificationAnimInstance.value = null
  }
}

const startClassificationAnimation = () => {
  if (!classificationAnimRef.value || classificationAnimInstance.value) return
  classificationAnimInstance.value = lottie.loadAnimation({
    container: classificationAnimRef.value,
    renderer: 'svg',
    loop: true,
    autoplay: true,
    animationData: fredThinkAnimation
  })
}

// Persist disambiguation items in sessionStorage so they survive page reloads.
// These are never written to the DB until the user resolves them, so without
// sessionStorage they would be lost on F5 / Ctrl+R.
const _savedDisambiguations = (() => {
  try { return JSON.parse(sessionStorage.getItem('fred_disambiguations') || '[]') } catch { return [] }
})()
const disambiguationItems = ref(_savedDisambiguations)

watch(disambiguationItems, (val) => {
  try { sessionStorage.setItem('fred_disambiguations', JSON.stringify(val)) } catch {}
}, { deep: true })

watch(isClassifying, async (value) => {
  if (value) {
    await nextTick()
    startClassificationAnimation()
  } else {
    destroyClassificationAnimation()
  }
})

// Helper function to capitalize food names properly
const capitalizeFoodName = (name) => {
  if (!name) return name
  // Split by spaces and capitalize each word
  return name.split(' ').map(word => 
    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  ).join(' ')
}

const hoursSinceEntryDate = (entryDate) => {
  if (!entryDate) return 0
  const parsed = new Date(entryDate)
  if (Number.isNaN(parsed.getTime())) return 0
  const hours = (Date.now() - parsed.getTime()) / (1000 * 60 * 60)
  return Math.max(0, Number(hours.toFixed(2)))
}

const formatTimeInFridge = (hours) => {
  const safeHours = Math.max(0, Number(hours) || 0)
  if (safeHours < 24) {
    const roundedHours = Math.round(safeHours)
    return `${roundedHours} hour${roundedHours === 1 ? '' : 's'}`
  }
  const roundedDays = Math.round(safeHours / 24)
  return `${roundedDays} day${roundedDays === 1 ? '' : 's'}`
}

// Computed property to check if on inventory page
const isOnInventoryPage = computed(() => route.path === '/inventory')

// Load pending items from database
const loadPendingItems = async () => {
  try {
    const response = await fetch(apiUrl('/api/foods/pending'))
    if (response.ok) {
      const pendingFoods = await response.json()
      
          // Convert database format to frontend format
      detectedItems.value = pendingFoods.map(food => ({
        id: food.id,
        predicted_class: food.name,
        prediction_source: food.predictionSource || null,
        gemini_error: food.geminiError || null,
        category: food.foodGroup,
        packaging_type: food.packagingType,
        storage_location: food.storageLocation,
        expiration_date: food.expirationDate,
        time_in_fridge: food.timeInFridge,
        days_until_spoilage: food.daysUntilSpoilage,
        freshness_score: food.freshnessScore,
        confidence: food.confidence || 95,
        top5: food.top5Predictions || [],
        timestamp: new Date().toLocaleTimeString(),
        isReentry: food.status === 'pending_reentry',
        entry_date: food.entryDate || '',
        description: food.description || '',
        safety_category: food.safetyCategory || '',
        warnings: food.warnings || [],
        cumulative_temp_abuse: food.cumulativeTempAbuse ?? 0,
        environment_alerts: food.environmentAlerts || []
      }))
    }
  } catch (error) {
    console.error('Error loading pending items:', error)
  }
}

const loadOutgoingItems = async () => {
  try {
    const response = await fetch(apiUrl('/api/foods/outgoing'))
    if (response.ok) {
      const outgoingFoods = await response.json()
      outgoingItems.value = outgoingFoods.map(food => ({
        id: food.id,
        name: food.name,
        foodGroup: food.foodGroup,
        packagingType: food.packagingType,
        storageLocation: food.storageLocation,
        expirationDate: food.expirationDate,
        freshnessScore: food.freshnessScore,
        daysUntilSpoilage: food.daysUntilSpoilage,
        timeInFridge: food.timeInFridge,
        entryDate: food.entryDate || '',
        description: food.description || '',
        safetyCategory: food.safetyCategory || '',
        warnings: food.warnings || [],
        cumulativeTempAbuse: food.cumulativeTempAbuse ?? 0,
        environmentAlerts: food.environmentAlerts || []
      }))
    }
  } catch (error) {
    console.error('Error loading outgoing items:', error)
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
    alert('No predictions were returned. Check browser DevTools Network for /api/classify-food/batch and backend logs for Gemini/API errors.')
    return
  }
  
  // Capitalize names for new scanned items
  const newItems = items.map(item => ({
    ...item,
    predicted_class: capitalizeFoodName(item.predicted_class)
  }))

  // Cache blobs and local model results keyed by food name for the comparison panel
  for (const item of newItems) {
    if (item.imageBlob) {
      imageBlobCache.value[item.predicted_class.toLowerCase()] = item.imageBlob
    }
    if (item.local_result !== undefined) {
      localResultCache.value[item.predicted_class.toLowerCase()] = item.local_result
    }
  }

  // Save items to database with 'pending' status.
  // We track which confirmed/removed IDs are already claimed by disambiguation
  // cards created earlier in this loop, so duplicate scans of the same item
  // don't all get the same disambiguation card.
  for (const item of newItems) {
    try {
      // Build claimed-ID sets from disambiguation cards accumulated so far
      // (both from previous sessions and from earlier iterations of this loop).
      // A slot is only "claimed" if it has been actively SELECTED by a card —
      // i.e. mark_outgoing(X) claims confirmed slot X, mark_reentry(Y) claims
      // removed slot Y.  Merely appearing in a card's match list does NOT claim
      // the slot, so the second scan of the same item can still get its own card
      // for the unclaimed slot (e.g. the confirmed item when the first card
      // defaulted to mark_reentry for the removed item).
      const claimedConfirmedIds = disambiguationItems.value
        .filter(d => d.selectedAction === 'mark_outgoing' && d.selectedTargetId)
        .map(d => d.selectedTargetId)
      const claimedRemovedIds = disambiguationItems.value
        .filter(d => d.selectedAction === 'mark_reentry' && d.selectedTargetId)
        .map(d => d.selectedTargetId)

      const payload = {
        name: item.predicted_class,
        foodGroup: item.category,
        predictionSource: item.prediction_source || null,
        geminiError: item.gemini_error || null,
        packagingType: item.packaging_type,
        storageLocation: item.storage_location,
        expirationDate: item.expiration_date || '',
        status: 'pending',
        confidence: item.confidence,
        top5Predictions: item.top5,
        daysInFridge: 0,
        cumulativeTempAbuse: 0,
        daysUntilSpoilage: parseInt(item.spoilage_parameters?.shelf_life_days) || 7,
        geminiSpoilageParams: item.spoilage_parameters || null,
        description: item.description || '',
        claimed_confirmed_ids: [...new Set(claimedConfirmedIds)],
        claimed_removed_ids: [...new Set(claimedRemovedIds)]
      }
      
      const response = await fetch(apiUrl('/api/foods'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })
      
      if (response.ok) {
        const result = await response.json()
        if (result.disambiguation) {
          // Don't write to DB yet — hold in memory until user resolves
          const defReentry = result.defaultReentryId || null
          const defOutgoing = result.defaultOutgoingId || null
          disambiguationItems.value.push({
            id: `disambiguation-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            ...result,
            scanData: payload,
            selectedAction: defReentry ? 'mark_reentry' : defOutgoing ? 'mark_outgoing' : null,
            selectedTargetId: defReentry || defOutgoing || null
          })
        }
        // matched / reentry / new pending: handled by loadPendingItems/loadOutgoingItems below
      } else {
        console.error('Failed to save pending item:', item.predicted_class)
      }
    } catch (error) {
      console.error('Error saving pending item:', error)
    }
  }
  
  // Reload all pending items from database (merges existing + new)
  await loadPendingItems()
  await loadOutgoingItems()
  
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
  selectedItem.value = {
    ...item,
    imageBlob: imageBlobCache.value[item.predicted_class?.toLowerCase()] ?? null,
    localResult: localResultCache.value[item.predicted_class?.toLowerCase()] ?? null
  }
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
        daysInFridge: (updatedData.timeInFridgeHours || 0) / 24,
        cumulativeTempAbuse: updatedData.timeOutsideFridgeHours,
        status: 'pending', // Keep as pending until "Add to Inventory" is clicked
        confidence: updatedData.confidence
      }
      
      const response = await fetch(apiUrl(`/api/foods/${item.id}`), {
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
              entry_date: new Date(Date.now() - ((updatedData.timeInFridgeHours || 0) * 60 * 60 * 1000)).toISOString(),
              time_in_fridge: formatTimeInFridge(updatedData.timeInFridgeHours),
              cumulative_temp_abuse: updatedData.timeOutsideFridgeHours,
              confidence: updatedData.confidence
            }
            return updatedItem
          }
          return i
        })
        // Update selectedItem to reference the new object (preserve blob for compare)
        if (updatedItem) {
          selectedItem.value = { ...updatedItem, imageBlob: selectedItem.value?.imageBlob ?? null }
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
      const response = await fetch(apiUrl(`/api/foods/${selectedItem.value.id}`), {
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

const handleSwitchToIncoming = async (itemId) => {
  try {
    const response = await fetch(apiUrl(`/api/foods/${itemId}/switch-to-incoming`), {
      method: 'POST'
    })
    if (response.ok) {
      // Reload both: outgoing item reverts to confirmed, pending item now appears
      await Promise.all([loadOutgoingItems(), loadPendingItems()])
    } else {
      console.error('Failed to switch item to incoming')
    }
  } catch (error) {
    console.error('Error switching item to incoming:', error)
  }
}

const handleMarkAsNew = async (itemId) => {
  try {
    const response = await fetch(apiUrl(`/api/foods/${itemId}/mark-as-new`), {
      method: 'POST'
    })
    if (response.ok) {
      await loadPendingItems()
    } else {
      console.error('Failed to mark item as new')
    }
  } catch (error) {
    console.error('Error marking item as new:', error)
  }
}

const handleResolveDisambiguation = (disambiguationId, action, targetId) => {
  const idx = disambiguationItems.value.findIndex(d => d.id === disambiguationId)
  if (idx === -1) return
  // Replace the object so Vue's deep watcher reliably detects the change
  disambiguationItems.value[idx] = {
    ...disambiguationItems.value[idx],
    selectedAction: action,
    selectedTargetId: targetId
  }

  // Cross-card coherence: when a sibling card has the same target selected,
  // deselect it so the same slot can't be claimed by two cards simultaneously.
  // (The user chose this slot here, so siblings should revert to unselected.)
  if (action === 'mark_outgoing' && targetId) {
    disambiguationItems.value = disambiguationItems.value.map((d, i) => {
      if (i === idx) return d
      if (d.selectedAction === 'mark_outgoing' && d.selectedTargetId === targetId) {
        return { ...d, selectedAction: null, selectedTargetId: null }
      }
      return d
    })
  } else if (action === 'mark_reentry' && targetId) {
    disambiguationItems.value = disambiguationItems.value.map((d, i) => {
      if (i === idx) return d
      if (d.selectedAction === 'mark_reentry' && d.selectedTargetId === targetId) {
        return { ...d, selectedAction: null, selectedTargetId: null }
      }
      return d
    })
  }
}

// For each disambiguation card, compute which of its option IDs are already
// selected (confirmed or pending OK) by a *sibling* card.
// Shape: { [cardId]: { confirmedIds: Set<string>, removedIds: Set<string> } }
const claimedByOthers = computed(() => {
  const result = {}
  for (const card of disambiguationItems.value) {
    const claimedConfirmed = new Set()
    const claimedRemoved = new Set()
    for (const sibling of disambiguationItems.value) {
      if (sibling.id === card.id) continue
      if (sibling.selectedAction === 'mark_outgoing' && sibling.selectedTargetId) {
        claimedConfirmed.add(sibling.selectedTargetId)
      }
      if (sibling.selectedAction === 'mark_reentry' && sibling.selectedTargetId) {
        claimedRemoved.add(sibling.selectedTargetId)
      }
    }
    result[card.id] = { confirmedIds: claimedConfirmed, removedIds: claimedRemoved }
  }
  return result
})

const handleOkDisambiguation = async (disambiguationId) => {
  const item = disambiguationItems.value.find(d => d.id === disambiguationId)
  if (!item || !item.selectedAction) return

  const payload = {
    action: item.selectedAction,
    target_id: item.selectedAction === 'mark_outgoing' ? item.selectedTargetId : null,
    removed_id: item.selectedAction === 'mark_reentry' ? item.selectedTargetId : null,
    scan_data: item.scanData,
    // The disambiguation type changes the meaning of mark_outgoing:
    //   reentry_or_outgoing → the scanned item is a NEW bar going in (not the removed one)
    //     → create a new pending item alongside the outgoing
    //   outgoing_or_new / multi_confirmed → the scan WAS of the outgoing item itself
    //     → no new pending item should be created
    dis_type: item.type
  }
  try {
    const resp = await fetch(apiUrl('/api/foods/resolve-disambiguation'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (resp.ok) {
      disambiguationItems.value = disambiguationItems.value.filter(d => d.id !== disambiguationId)
      await Promise.all([loadPendingItems(), loadOutgoingItems()])
    } else {
      console.error('Failed to resolve disambiguation')
    }
  } catch (e) {
    console.error('Error resolving disambiguation:', e)
  }
}

const handleRejectAll = () => {
  showRejectConfirm.value = true
}

const confirmRejectAll = async () => {
  try {
    const pendingResp = await fetch(apiUrl('/api/foods/pending/delete'), { method: 'DELETE' })
    if (pendingResp.ok) {
      detectedItems.value = []
      showRejectConfirm.value = false
    } else {
      console.error('Failed to delete pending items')
    }
    const outgoingResp = await fetch(apiUrl('/api/foods/outgoing/restore'), { method: 'POST' })
    if (outgoingResp.ok) {
      outgoingItems.value = []
    }
    // Dismiss all disambiguation cards — the scans that generated them are discarded
    disambiguationItems.value = []
  } catch (error) {
    console.error('Error rejecting all items:', error)
  }
}

const cancelRejectAll = () => {
  showRejectConfirm.value = false
}

const closeItemList = async () => {
  try {
    // Disambiguation items are resolved individually via their OK button before
    // this function can be called (Confirm All is disabled while any remain).
    // Nothing to do here for disambiguations.

    // Confirm pending items
    if (detectedItems.value.length > 0) {
      const confirmResp = await fetch(apiUrl('/api/foods/pending/confirm'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      if (confirmResp.ok) {
        detectedItems.value = []
      } else {
        alert('Failed to add items to inventory')
      }
    }

    // Delete outgoing items
    if (outgoingItems.value.length > 0) {
      const outgoingResp = await fetch(apiUrl('/api/foods/outgoing/delete'), { method: 'DELETE' })
      if (outgoingResp.ok) {
        outgoingItems.value = []
      }
    }

    await Promise.all([loadPendingItems(), loadOutgoingItems()])
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
  loadOutgoingItems()
  geminiEnabled.value = loadGeminiPreference()

  const wantsFullscreen = loadFullscreenPreference()
  isFullscreen.value = Boolean(document.fullscreenElement)
  if (wantsFullscreen && !document.fullscreenElement) {
    shouldRestoreFullscreen.value = true
    addFullscreenRestoreListeners()
  }

  window.addEventListener('keydown', handleKeyDown)
  document.addEventListener('fullscreenchange', syncFullscreenState)
})

onUnmounted(() => {
  destroyClassificationAnimation()
  window.removeEventListener('keydown', handleKeyDown)
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  removeFullscreenRestoreListeners()
})
</script>

<template>
  <SidebarProvider class="sidebar-provider">
    <AppSidebar :gemini-enabled="geminiEnabled" @toggle-gemini="setGeminiEnabled" />
    <div class="content-wrapper">
      <SidebarTrigger class="sidebar-trigger" />
      
      <main>
        <div class="top-right-controls">
          <button class="scan-quick-btn" @click="openCameraPopup" title="Open scanner">scan</button>
          <button
            class="fullscreen-corner-btn"
            @click="toggleFullscreen"
            :aria-pressed="isFullscreen.toString()"
            :aria-label="isFullscreen ? 'Exit full screen' : 'Enter full screen'"
            :title="isFullscreen ? 'Exit full screen' : 'Enter full screen'"
          >
            <span class="fs-icon" :class="{ inward: isFullscreen }" aria-hidden="true">
              <span class="corner tl"></span>
              <span class="corner tr"></span>
              <span class="corner bl"></span>
              <span class="corner br"></span>
            </span>
          </button>
        </div>

        <header class="global-header">
          <RouterLink to="/" class="global-logo-link" aria-label="Go to home page">
            <img :src="appLogo" alt="FRED logo" class="global-logo" />
          </RouterLink>
        </header>

        <!-- Pending Items Banner -->
        <div v-if="detectedItems.length > 0 || outgoingItems.length > 0 || disambiguationItems.length > 0" class="pending-banner">
          <div class="banner-content">
            <div class="banner-info">
              <span class="banner-icon">⚠️</span>
              <span class="banner-text">
                <template v-if="disambiguationItems.length > 0">{{ disambiguationItems.length }} Item{{ disambiguationItems.length > 1 ? 's' : '' }} Need{{ disambiguationItems.length > 1 ? '' : 's' }} Attention</template>
                <template v-if="disambiguationItems.length > 0 && (detectedItems.length > 0 || outgoingItems.length > 0)"> · </template>
                <template v-if="detectedItems.length > 0">{{ detectedItems.length }} Item{{ detectedItems.length > 1 ? 's' : '' }} Pending</template>
                <template v-if="detectedItems.length > 0 && outgoingItems.length > 0"> · </template>
                <template v-if="outgoingItems.length > 0">{{ outgoingItems.length }} Item{{ outgoingItems.length > 1 ? 's' : '' }} Outgoing</template>
              </span>
            </div>
            <div class="banner-actions">
              <button v-if="!isOnInventoryPage" class="banner-button view-button" @click="navigateToInventory">
                View
              </button>
              <template v-else>
                <button
                  class="banner-button reject-button"
                  :title="disambiguationItems.length > 0 ? 'Resolve all disambiguation cards first' : ''"
                  @click="handleRejectAll"
                >
                  Reject All
                </button>
                <button
                  class="banner-button add-button"
                  :disabled="disambiguationItems.length > 0"
                  :title="disambiguationItems.length > 0 ? 'Resolve all disambiguation cards first' : ''"
                  @click="closeItemList"
                >
                  Confirm All
                </button>
              </template>
            </div>
          </div>
        </div>
        
        <RouterView v-slot="{ Component }">
          <keep-alive include="Inventory">
            <component
              :is="Component"
              :pending-items="detectedItems"
              :outgoing-items="outgoingItems"
              :disambiguation-items="disambiguationItems"
              :claimed-by-others="claimedByOthers"
              @view-pending-item="handleViewPendingItem"
              @switch-to-incoming="handleSwitchToIncoming"
              @mark-as-new="handleMarkAsNew"
              @resolve-disambiguation="handleResolveDisambiguation"
              @ok-disambiguation="handleOkDisambiguation"
            />
          </keep-alive>
        </RouterView>
      </main>
      <div class="right-spacer"></div>
    </div>
    
    <!-- Global Camera Popup -->
    <CameraCapture 
      v-if="showCameraPopup"
      :gemini-enabled="geminiEnabled"
      @close="closeCameraPopup"
      @finish="handleFinishScanning"
      @classifying="handleClassifying"
    />
    
    <!-- Global Results Popup -->
    <FoodScanResults
      v-if="showResultsPopup && selectedItem"
      :predicted-class="selectedItem.predicted_class"
      :confidence="selectedItem.confidence"
      :top5="selectedItem.top5"
      :prediction-source="selectedItem.prediction_source"
      :gemini-error="selectedItem.gemini_error"
      :category="selectedItem.category"
      :packaging-type="selectedItem.packaging_type"
      :storage-location="selectedItem.storage_location"
      :expiration-date="selectedItem.expiration_date"
      :time-in-fridge-hours="hoursSinceEntryDate(selectedItem.entry_date)"
      :time-outside-fridge-hours="Number(selectedItem.cumulative_temp_abuse ?? 0)"
      :notes="selectedItem.notes"
      :image-blob="selectedItem.imageBlob ?? null"
      :local-result="selectedItem.localResult ?? null"
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
        <div ref="classificationAnimRef" class="classification-animation"></div>
        <p class="loading-text">Identifying {{ classifyingCount === 1 ? 'item' : 'items' }}...</p>
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
  --top-control-offset: 1rem;
  --side-control-offset: 1rem;
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: auto;
  padding-bottom: 2rem;
}

.sidebar-trigger {
  flex-shrink: 0;
  padding: var(--top-control-offset) var(--side-control-offset);
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

.global-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1.25rem 0 1rem 0;
}

.top-right-controls {
  position: fixed;
  top: var(--top-control-offset);
  right: var(--side-control-offset);
  z-index: 120;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.scan-quick-btn {
  height: 2.5rem;
  padding: 0 0.8rem;
  border: 1px solid oklch(0.35 0.03 260);
  border-radius: 0.7rem;
  background: oklch(0.2 0.02 250);
  color: oklch(0.92 0.01 250);
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: lowercase;
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease, transform 140ms ease;
}

.scan-quick-btn:hover {
  background: oklch(0.28 0.03 250);
  border-color: oklch(0.55 0.05 260);
  transform: translateY(-1px);
}

.scan-quick-btn:focus-visible {
  outline: 2px solid oklch(0.7 0.14 250);
  outline-offset: 2px;
}

.fullscreen-corner-btn {
  width: 2.5rem;
  height: 2.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid oklch(0.35 0.03 260);
  border-radius: 0.7rem;
  background: oklch(0.2 0.02 250);
  color: oklch(0.92 0.01 250);
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease, transform 140ms ease;
}

.fullscreen-corner-btn:hover {
  background: oklch(0.28 0.03 250);
  border-color: oklch(0.55 0.05 260);
  transform: translateY(-1px);
}

.fullscreen-corner-btn:focus-visible {
  outline: 2px solid oklch(0.7 0.14 250);
  outline-offset: 2px;
}

.fs-icon {
  position: relative;
  width: 1.15rem;
  height: 1.15rem;
}

.corner {
  position: absolute;
  width: 0.42rem;
  height: 0.42rem;
  border-color: currentColor;
  border-style: solid;
  border-width: 0;
}

.corner.tl {
  top: 0;
  left: 0;
  border-top-width: 2px;
  border-left-width: 2px;
}

.corner.tr {
  top: 0;
  right: 0;
  border-top-width: 2px;
  border-right-width: 2px;
}

.corner.bl {
  bottom: 0;
  left: 0;
  border-bottom-width: 2px;
  border-left-width: 2px;
}

.corner.br {
  bottom: 0;
  right: 0;
  border-bottom-width: 2px;
  border-right-width: 2px;
}

.fs-icon.inward .corner.tl {
  top: 0.06rem;
  left: 0.06rem;
  width: 0.3rem;
  height: 0.3rem;
  border-top-width: 0;
  border-left-width: 0;
  border-right-width: 2px;
  border-bottom-width: 2px;
}

.fs-icon.inward .corner.tr {
  top: 0.06rem;
  right: 0.06rem;
  width: 0.3rem;
  height: 0.3rem;
  border-top-width: 0;
  border-right-width: 0;
  border-left-width: 2px;
  border-bottom-width: 2px;
}

.fs-icon.inward .corner.bl {
  bottom: 0.06rem;
  left: 0.06rem;
  width: 0.3rem;
  height: 0.3rem;
  border-bottom-width: 0;
  border-left-width: 0;
  border-top-width: 2px;
  border-right-width: 2px;
}

.fs-icon.inward .corner.br {
  bottom: 0.06rem;
  right: 0.06rem;
  width: 0.3rem;
  height: 0.3rem;
  border-bottom-width: 0;
  border-right-width: 0;
  border-top-width: 2px;
  border-left-width: 2px;
}

@media (max-width: 768px) {
  .content-wrapper {
    --top-control-offset: 0.75rem;
    --side-control-offset: 0.75rem;
  }

  .top-right-controls {
    gap: 0.4rem;
  }

  .fullscreen-corner-btn {
    width: 2.25rem;
    height: 2.25rem;
  }

  .scan-quick-btn {
    height: 2.25rem;
    padding: 0 0.65rem;
    font-size: 0.8rem;
  }
}

.global-logo {
  width: min(420px, 62vw);
  height: auto;
  display: block;
}

.global-logo-link {
  display: inline-flex;
  cursor: pointer;
  text-decoration: none;
}

.global-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: oklch(0.92 0.02 250);
  text-align: center;
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

.classification-animation {
  width: min(380px, 78vw);
  height: min(380px, 78vw);
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
  background: oklch(0.14 0 0);
  border: 2px solid oklch(0.55 0.2 45);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  margin: 0 0 1rem 0;
  position: sticky;
  top: 0;
  z-index: 50;
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

.add-button:hover:not(:disabled) {
  background: oklch(0.7 0.22 145);
  transform: translateY(-1px);
  box-shadow: 0 3px 10px rgba(0, 255, 100, 0.3);
}

.banner-button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

.reject-button {
  background: oklch(0.55 0.2 25);
  color: oklch(0.95 0 0);
}

.reject-button:hover:not(:disabled) {
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

  .global-logo {
    width: min(340px, 74vw);
  }
}

@media (max-width: 480px) {
  .sidebar-trigger {
    padding: 0.5rem;
  }

  main {
    padding: 0.75rem;
  }

  .global-logo {
    width: min(280px, 82vw);
  }
}
</style>
