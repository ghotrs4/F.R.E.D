<!--

-->

<script setup>
import { ref, shallowRef, onMounted, onUnmounted, computed } from 'vue'
import { ObjectDetector, FilesetResolver } from '@mediapipe/tasks-vision'
import { apiUrl } from '../utils/apiBase'

const emit = defineEmits(['close', 'finish', 'classifying'])
const props = defineProps({
  geminiEnabled: {
    type: Boolean,
    default: true
  },
  useLocalCamera: {
    type: Boolean,
    default: false
  }
})

const videoRef = ref(null)
const streamImageRef = ref(null)
const canvasRef = ref(null)
const stream = ref(null)
const cameraMode = computed(() => (props.useLocalCamera ? 'local' : 'pi'))
const isCameraActive = ref(false)
const error = ref(null)
const model = shallowRef(null)
const detectionInterval = ref(null)
const objectDetected = ref(false)
const isModelLoading = ref(true)
const countdown = ref(null)
const countdownTimer = ref(null)
const isCapturing = ref(false)
const capturedBlobs = ref([])
const statusMessage = ref('')
const isBatchProcessing = ref(false)
const batchProgress = ref({ current: 0, total: 0 })
const captureCooldown = ref(false)
const localFacingMode = ref('environment')
const isSwitchingLocalCamera = ref(false)
const localVideoInputCount = ref(0)
const debugCanvasRef = ref(null)
const guideBoxRef = ref(null)
const showDebugOverlay = ref(false)
const tapTimer = ref(null)
const lastTapTimestamp = ref(0)
const lastGestureTimestamp = ref(0)
const piStreamNonce = ref(Date.now())
const piDetectionCanvas = ref(null)
const piDetectionCtx = ref(null)
const piStreamActive = ref(false)

const piStreamUrl = computed(() => {
  if (!piStreamActive.value) return ''
  return `${apiUrl('/api/camera/stream')}?t=${piStreamNonce.value}`
})

const canSwitchLocalCamera = computed(() => cameraMode.value === 'local' && localVideoInputCount.value !== 1)

const DOUBLE_TAP_WINDOW_MS = 280
const GESTURE_DEDUPE_MS = 80

const clearTapTimer = () => {
  if (tapTimer.value) {
    clearTimeout(tapTimer.value)
    tapTimer.value = null
  }
}

const registerFrameTap = () => {
  if (isBatchProcessing.value) return

  const now = Date.now()
  const isDoubleTap = now - lastTapTimestamp.value <= DOUBLE_TAP_WINDOW_MS

  if (isDoubleTap) {
    clearTapTimer()
    lastTapTimestamp.value = 0
    toggleDebugOverlay()
    return
  }

  lastTapTimestamp.value = now
  clearTapTimer()
  tapTimer.value = setTimeout(() => {
    if (!isBatchProcessing.value && !captureCooldown.value) {
      captureImage()
    }
    tapTimer.value = null
    lastTapTimestamp.value = 0
  }, DOUBLE_TAP_WINDOW_MS)
}

const handleFramePointerDown = (event) => {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  const now = Date.now()
  if (now - lastGestureTimestamp.value < GESTURE_DEDUPE_MS) return
  lastGestureTimestamp.value = now
  registerFrameTap()
}

const handleFrameClick = () => {
  const now = Date.now()
  if (now - lastGestureTimestamp.value < GESTURE_DEDUPE_MS) return
  lastGestureTimestamp.value = now
  registerFrameTap()
}

const handleFrameMouseDown = (event) => {
  if (event.button !== 0) return
  const now = Date.now()
  if (now - lastGestureTimestamp.value < GESTURE_DEDUPE_MS) return
  lastGestureTimestamp.value = now
  registerFrameTap()
}

const handleFrameTouchStart = (event) => {
  // Fallback for browsers that do not emit PointerEvents consistently.
  event.preventDefault()
  const now = Date.now()
  if (now - lastGestureTimestamp.value < GESTURE_DEDUPE_MS) return
  lastGestureTimestamp.value = now
  registerFrameTap()
}

const toggleDebugOverlay = () => {
  showDebugOverlay.value = !showDebugOverlay.value
  statusMessage.value = showDebugOverlay.value ? 'Debug overlay enabled' : ''
  if (showDebugOverlay.value) {
    setTimeout(() => {
      if (statusMessage.value === 'Debug overlay enabled') {
        statusMessage.value = ''
      }
    }, 1200)
  }
  // Clear canvas immediately when turning off
  if (!showDebugOverlay.value) {
    const debugCanvas = debugCanvasRef.value
    if (debugCanvas) {
      debugCanvas.getContext('2d').clearRect(0, 0, debugCanvas.width, debugCanvas.height)
    }
  }
}

const startCamera = async () => {
  error.value = null

  if (cameraMode.value === 'pi') {
    stopDetection()
    stopLocalCamera()
    piStreamActive.value = true
    piStreamNonce.value = Date.now()
    isCameraActive.value = true
    return
  }

  await startLocalCamera()
}

const refreshVideoInputCount = async () => {
  if (!navigator.mediaDevices?.enumerateDevices) {
    localVideoInputCount.value = 0
    return
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    localVideoInputCount.value = devices.filter(device => device.kind === 'videoinput').length
  } catch (e) {
    console.warn('Unable to enumerate video devices:', e)
    localVideoInputCount.value = 0
  }
}

const startLocalCamera = async () => {
  const baseVideoConstraints = {
    width: { ideal: 1280 },
    height: { ideal: 720 }
  }

  try {
    stream.value = await navigator.mediaDevices.getUserMedia({
      video: {
        ...baseVideoConstraints,
        facingMode: { ideal: localFacingMode.value }
      }
    })
  } catch (e) {
    if (e?.name === 'OverconstrainedError' || e?.name === 'NotFoundError') {
      // Fallback for browsers/devices that do not support facingMode selection.
      try {
        stream.value = await navigator.mediaDevices.getUserMedia({
          video: baseVideoConstraints
        })
      } catch (fallbackError) {
        error.value = 'Failed to access camera. Please ensure camera permissions are granted.'
        console.error('Camera error:', fallbackError)
        return false
      }
    } else {
      error.value = 'Failed to access camera. Please ensure camera permissions are granted.'
      console.error('Camera error:', e)
      return false
    }
  }

  try {
    if (videoRef.value) {
      videoRef.value.srcObject = stream.value
      isCameraActive.value = true
      error.value = null
      const activeTrack = stream.value?.getVideoTracks()?.[0]
      const facing = activeTrack?.getSettings?.().facingMode
      if (facing === 'environment' || facing === 'user') {
        localFacingMode.value = facing
      }
      await refreshVideoInputCount()
      startDetection()
    }
    return true
  } catch (e) {
    error.value = 'Failed to access camera. Please ensure camera permissions are granted.'
    console.error('Camera error:', e)
    return false
  }
}

const switchLocalCamera = async () => {
  if (cameraMode.value !== 'local' || isSwitchingLocalCamera.value || isBatchProcessing.value) return

  isSwitchingLocalCamera.value = true
  const nextFacingMode = localFacingMode.value === 'environment' ? 'user' : 'environment'
  localFacingMode.value = nextFacingMode
  statusMessage.value = `Switching to ${nextFacingMode === 'environment' ? 'back' : 'front'} camera...`

  stopDetection()
  stopLocalCamera()
  isCameraActive.value = false

  const switched = await startLocalCamera()
  if (switched) {
    statusMessage.value = `Using ${localFacingMode.value === 'environment' ? 'back' : 'front'} camera`
    setTimeout(() => {
      if (statusMessage.value.startsWith('Using ')) {
        statusMessage.value = ''
      }
    }, 1200)
  }

  isSwitchingLocalCamera.value = false
}

const stopLocalCamera = () => {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
  }
  if (videoRef.value) {
    videoRef.value.srcObject = null
  }
}

const stopPiStream = () => {
  piStreamActive.value = false
  // Aggressively clear src so the browser closes the HTTP stream immediately.
  if (streamImageRef.value) {
    streamImageRef.value.removeAttribute('src')
    streamImageRef.value.src = ''
  }
}

const stopCamera = () => {
  stopPiStream()
  stopLocalCamera()
  isCameraActive.value = false
  stopDetection()
}

const onPiStreamLoaded = () => {
  isCameraActive.value = true
  error.value = null
  startDetection()
}

const onPiStreamError = () => {
  isCameraActive.value = false
  error.value = 'Failed to load Raspberry Pi camera stream. Check backend proxy and Pi stream service.'
  stopDetection()
}

const startCountdown = () => {
  if (countdownTimer.value) return // Already counting down
  
  isCapturing.value = true
  countdown.value = 1
  
  countdownTimer.value = setInterval(() => {
    countdown.value--
    
    if (countdown.value === 0) {
      // Auto-capture!
      clearInterval(countdownTimer.value)
      countdownTimer.value = null
      isCapturing.value = false
      captureImage()
    }
  }, 1000) // Decrease every second
}

const cancelCountdown = () => {
  if (countdownTimer.value) {
    clearInterval(countdownTimer.value)
    countdownTimer.value = null
    countdown.value = null
    isCapturing.value = false
  }
}

const captureImage = () => {
  if (!canvasRef.value || isBatchProcessing.value) return

  const canvas = canvasRef.value
  const context = canvas.getContext('2d')
  const sourceElement = cameraMode.value === 'pi' ? streamImageRef.value : videoRef.value

  if (!sourceElement) return

  const sourceWidth = cameraMode.value === 'pi'
    ? sourceElement.naturalWidth
    : sourceElement.videoWidth
  const sourceHeight = cameraMode.value === 'pi'
    ? sourceElement.naturalHeight
    : sourceElement.videoHeight

  const displayWidth = sourceElement.clientWidth
  const displayHeight = sourceElement.clientHeight

  if (!sourceWidth || !sourceHeight || !displayWidth || !displayHeight) return

  const guideWidth = guideBoxRef.value?.clientWidth || 300
  const guideHeight = guideBoxRef.value?.clientHeight || 300
  const guideLeft = (displayWidth - guideWidth) / 2
  const guideTop = (displayHeight - guideHeight) / 2

  const scaleX = sourceWidth / displayWidth
  const scaleY = sourceHeight / displayHeight

  let cropX = Math.round(guideLeft * scaleX)
  let cropY = Math.round(guideTop * scaleY)
  let cropWidth = Math.round(guideWidth * scaleX)
  let cropHeight = Math.round(guideHeight * scaleY)

  cropX = Math.max(0, Math.min(cropX, sourceWidth - 1))
  cropY = Math.max(0, Math.min(cropY, sourceHeight - 1))
  cropWidth = Math.max(1, Math.min(cropWidth, sourceWidth - cropX))
  cropHeight = Math.max(1, Math.min(cropHeight, sourceHeight - cropY))

  if (cameraMode.value === 'pi') {
    const streamImage = streamImageRef.value
    if (!streamImage || !streamImage.naturalWidth || !streamImage.naturalHeight) {
      statusMessage.value = 'Pi stream is not ready yet. Try again in a second.'
      setTimeout(() => {
        if (statusMessage.value === 'Pi stream is not ready yet. Try again in a second.') {
          statusMessage.value = ''
        }
      }, 1500)
      return
    }
  } else {
    const video = videoRef.value
    if (!video || !video.videoWidth || !video.videoHeight) return
  }

  canvas.width = cropWidth
  canvas.height = cropHeight
  context.drawImage(
    sourceElement,
    cropX,
    cropY,
    cropWidth,
    cropHeight,
    0,
    0,
    cropWidth,
    cropHeight
  )
  
  canvas.toBlob((blob) => {
    if (blob) {
      capturedBlobs.value.push(blob)
      statusMessage.value = `Item ${capturedBlobs.value.length} captured!`
      objectDetected.value = false
      captureCooldown.value = true
      setTimeout(() => {
        captureCooldown.value = false
        statusMessage.value = ''
      }, 2000)
    }
  }, 'image/jpeg', 0.95)
}

const finishScanning = async () => {
  if (capturedBlobs.value.length === 0) {
    stopCamera()
    emit('finish', [])
    return
  }
  
  isBatchProcessing.value = true
  emit('classifying', capturedBlobs.value.length)
  batchProgress.value = { current: 0, total: capturedBlobs.value.length }
  stopCamera()
  
  try {
    const formData = new FormData()
    formData.append('gemini_enabled', props.geminiEnabled ? 'true' : 'false')
    capturedBlobs.value.forEach((blob, i) => {
      formData.append(`image_${i}`, blob, `capture_${i}.jpg`)
    })

    const response = await fetch(apiUrl('/api/classify-food/batch'), {
      method: 'POST',
      body: formData
    })
    
    const results = []
    if (!response.ok) {
      let backendMessage = ''
      try {
        const errorPayload = await response.json()
        backendMessage = errorPayload?.error || JSON.stringify(errorPayload)
      } catch {
        backendMessage = await response.text()
      }
      throw new Error(`Batch classification failed (${response.status}): ${backendMessage || 'unknown error'}`)
    }

    const classifications = await response.json()
    const items = Array.isArray(classifications) ? classifications : []
    items.forEach((result, index) => {
      if (
        result.predicted_class &&
        result.predicted_class.toLowerCase() !== 'no food detected' &&
        !result.error
      ) {
        results.push({
          id: Date.now() + results.length,
          timestamp: new Date().toLocaleTimeString(),
          ...result,
          imageBlob: capturedBlobs.value[index] ?? null
        })
      }
    })

    batchProgress.value = { current: capturedBlobs.value.length, total: capturedBlobs.value.length }
    emit('finish', results)
  } catch (err) {
    console.error('Batch classification error:', err)
    emit('finish', [])
  } finally {
    emit('classifying', false)
    isBatchProcessing.value = false
  }
}

const startDetection = () => {
  if (!model.value) {
    console.log('Detection not started: model not loaded')
    return
  }

  if (detectionInterval.value) {
    clearInterval(detectionInterval.value)
    detectionInterval.value = null
  }
  
  console.log('Starting detection...')
  
  detectionInterval.value = setInterval(() => {
    const sourceElement = cameraMode.value === 'pi' ? streamImageRef.value : videoRef.value
    if (!sourceElement) return

    if (cameraMode.value === 'local') {
      if (!videoRef.value || videoRef.value.readyState !== 4) return
    } else if (!streamImageRef.value?.naturalWidth || !streamImageRef.value?.naturalHeight) {
      return
    }
    
    try {
      let detectionSource = sourceElement
      if (cameraMode.value === 'pi') {
        const sourceWidth = streamImageRef.value.naturalWidth
        const sourceHeight = streamImageRef.value.naturalHeight
        if (!sourceWidth || !sourceHeight) return

        if (!piDetectionCanvas.value) {
          piDetectionCanvas.value = document.createElement('canvas')
          piDetectionCtx.value = piDetectionCanvas.value.getContext('2d')
        }
        if (!piDetectionCtx.value) return

        if (piDetectionCanvas.value.width !== sourceWidth || piDetectionCanvas.value.height !== sourceHeight) {
          piDetectionCanvas.value.width = sourceWidth
          piDetectionCanvas.value.height = sourceHeight
        }
        piDetectionCtx.value.drawImage(streamImageRef.value, 0, 0, sourceWidth, sourceHeight)
        detectionSource = piDetectionCanvas.value
      }

      const raw = model.value.detect(detectionSource)
      // Normalise to the same {class, score, bbox:[x,y,w,h]} shape used downstream
      const predictions = raw.detections.map(d => ({
        class: d.categories[0]?.categoryName ?? '',
        score: d.categories[0]?.score ?? 0,
        bbox: [
          d.boundingBox.originX,
          d.boundingBox.originY,
          d.boundingBox.width,
          d.boundingBox.height
        ]
      }))
      
      // Get source dimensions
      const sourceWidth = cameraMode.value === 'pi'
        ? streamImageRef.value.naturalWidth
        : videoRef.value.videoWidth
      const sourceHeight = cameraMode.value === 'pi'
        ? streamImageRef.value.naturalHeight
        : videoRef.value.videoHeight
      
      // Calculate guide box boundaries in video coordinates
      // Guide box is 300x300px centered on the display, but we need to map to actual video size
      const displayWidth = sourceElement.clientWidth
      const displayHeight = sourceElement.clientHeight

      if (!displayWidth || !displayHeight || !sourceWidth || !sourceHeight) return
      
      // Scale factor from display to video
      const scaleX = sourceWidth / displayWidth
      const scaleY = sourceHeight / displayHeight
      
      // Guide box dimensions in display coordinates
      const guideBoxSize = 300
      const guideBoxLeft = (displayWidth - guideBoxSize) / 2
      const guideBoxTop = (displayHeight - guideBoxSize) / 2
      const guideBoxRight = guideBoxLeft + guideBoxSize
      const guideBoxBottom = guideBoxTop + guideBoxSize
      
      // Convert to video coordinates
      const videoGuideBoxLeft = guideBoxLeft * scaleX
      const videoGuideBoxTop = guideBoxTop * scaleY
      const videoGuideBoxRight = guideBoxRight * scaleX
      const videoGuideBoxBottom = guideBoxBottom * scaleY
      
      // Filter predictions to only those centered in the guide box,
      // excluding 'person' detections entirely.
      const centeredPredictions = predictions.filter(p => {
        // if (p.class === 'person') return false
        // p.bbox is [x, y, width, height]
        const objLeft = p.bbox[0]
        const objTop = p.bbox[1]
        const objWidth = p.bbox[2]
        const objHeight = p.bbox[3]
        const objRight = objLeft + objWidth
        const objBottom = objTop + objHeight
        
        // Calculate center point
        const centerX = objLeft + objWidth / 2
        const centerY = objTop + objHeight / 2
        
        // Calculate overlap area between object and guide box
        const overlapLeft = Math.max(objLeft, videoGuideBoxLeft)
        const overlapTop = Math.max(objTop, videoGuideBoxTop)
        const overlapRight = Math.min(objRight, videoGuideBoxRight)
        const overlapBottom = Math.min(objBottom, videoGuideBoxBottom)
        
        // Check if there's any overlap
        if (overlapLeft >= overlapRight || overlapTop >= overlapBottom) {
          return false // No overlap
        }
        
        // Calculate overlap area
        const overlapArea = (overlapRight - overlapLeft) * (overlapBottom - overlapTop)
        const objectArea = objWidth * objHeight
        const guideBoxArea = guideBoxSize * guideBoxSize * scaleX * scaleY
        
        // Require at least 60% of object to be inside guide box AND center must be inside
        const overlapPercentage = overlapArea / objectArea
        const centerInside = centerX >= videoGuideBoxLeft && 
                           centerX <= videoGuideBoxRight &&
                           centerY >= videoGuideBoxTop && 
                           centerY <= videoGuideBoxBottom

        // Foreground check: object must fill at least 25% of the guide box
        const guideFillPercentage = overlapArea / guideBoxArea

        return overlapPercentage > 0.6 && centerInside && guideFillPercentage > 0.25
      })

      // --- Debug overlay: draw all detection bounding boxes ---
      const debugCanvas = debugCanvasRef.value
      if (debugCanvas && showDebugOverlay.value) {
        debugCanvas.width = displayWidth
        debugCanvas.height = displayHeight
        const ctx = debugCanvas.getContext('2d')
        ctx.clearRect(0, 0, displayWidth, displayHeight)
        const guideBoxAreaDisplay = guideBoxSize * guideBoxSize

        // Always draw debug guide and state so toggle feedback is visible
        ctx.strokeStyle = '#22d3ee'
        ctx.lineWidth = 2
        ctx.setLineDash([8, 6])
        ctx.strokeRect(guideBoxLeft, guideBoxTop, guideBoxSize, guideBoxSize)
        ctx.setLineDash([])
        ctx.font = 'bold 12px monospace'
        ctx.fillStyle = '#22d3ee'
        ctx.fillText(`DEBUG ON | source=${cameraMode.value} | detections=${predictions.length}`, 10, 18)

        for (const p of predictions) {
          const x = p.bbox[0] / scaleX
          const y = p.bbox[1] / scaleY
          const w = p.bbox[2] / scaleX
          const h = p.bbox[3] / scaleY
          const isCentered = centeredPredictions.includes(p)
          // Guide fill % in display coords for label
          const ix = Math.max(x, guideBoxLeft)
          const iy = Math.max(y, guideBoxTop)
          const iw = Math.min(x + w, guideBoxRight) - ix
          const ih = Math.min(y + h, guideBoxBottom) - iy
          const fillPct = (iw > 0 && ih > 0) ? Math.round((iw * ih) / guideBoxAreaDisplay * 100) : 0
          // Green = passes all checks, yellow = outside/too small
          ctx.strokeStyle = isCentered ? '#00ff88' : '#facc15'
          ctx.lineWidth = 2
          ctx.strokeRect(x, y, w, h)
          const label = `${p.class} ${Math.round(p.score * 100)}% fill:${fillPct}%`
          ctx.font = 'bold 12px monospace'
          ctx.fillStyle = isCentered ? '#00ff88' : '#facc15'
          const labelY = y > 18 ? y - 4 : y + h + 14
          ctx.fillText(label, x + 2, labelY)
        }

        if (!predictions.length) {
          ctx.fillStyle = '#facc15'
          ctx.fillText('No detections on this frame', 10, 36)
        }
      }

      // Check if any object detected with reasonable confidence in the center box
      const detected = centeredPredictions.some(p => p.score > 0.2)
      
      // Don't start new countdown if batch processing or in post-capture cooldown
      if (detected && !objectDetected.value && !isBatchProcessing.value && !captureCooldown.value) {
        // Object just appeared - start countdown
        console.log('Object detected in center - starting countdown')
        objectDetected.value = true
        startCountdown()
      } else if (!detected && objectDetected.value && !isBatchProcessing.value) {
        // Object disappeared - cancel countdown
        console.log('Object left center frame - canceling countdown')
        objectDetected.value = false
        cancelCountdown()
      }
    } catch (e) {
      console.error('Detection error:', e)
    }
  }, 100) // Check every 100ms
}

const stopDetection = () => {
  if (detectionInterval.value) {
    clearInterval(detectionInterval.value)
    detectionInterval.value = null
  }
  cancelCountdown()
  objectDetected.value = false
  // Clear debug overlay
  const debugCanvas = debugCanvasRef.value
  if (debugCanvas) {
    debugCanvas.getContext('2d').clearRect(0, 0, debugCanvas.width, debugCanvas.height)
  }
}

const close = () => {
  clearTapTimer()
  stopCamera()
  emit('close')
}

const handleKeyDown = (event) => {
  if (isBatchProcessing.value) return

  if (event.key === 'Escape') {
    close()
  } else if (event.key === 'Enter' && !isBatchProcessing.value) {
    finishScanning()
  } else if (event.key === 'd' || event.key === 'D') {
    toggleDebugOverlay()
  } else if ((event.key === 'c' || event.key === 'C') && !isBatchProcessing.value && !captureCooldown.value) {
    captureImage()
  }
}

onMounted(async () => {
  await refreshVideoInputCount()
  // Load MediaPipe EfficientDet model (all assets served locally)
  try {
    const vision = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
    model.value = await ObjectDetector.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: '/mediapipe/efficientdet_lite0.tflite',
        delegate: 'GPU'
      },
      scoreThreshold: 0.1,
      runningMode: 'IMAGE',
      categoryDenylist: ["person"]
    })
    isModelLoading.value = false
  } catch (e) {
    console.error('Failed to load detection model:', e)
    isModelLoading.value = false
  }
  
  // Start camera after model is loaded
  startCamera()
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  clearTapTimer()
  stopCamera()
  window.removeEventListener('keydown', handleKeyDown)
})
</script>

<template>
  <div v-if="!isBatchProcessing" class="camera-popup-overlay" @click="close">
    <div class="camera-popup-content" @click.stop>
      <div class="camera-header">
        <h2>Scan Food Item</h2>
        <button class="close-button" @click="close">&times;</button>
      </div>
      
      <div class="camera-body">
        <div v-if="isModelLoading" class="camera-loading">
          <div class="spinner"></div>
          <p>Loading detection model...</p>
        </div>
        
        <div v-else-if="error" class="camera-error">
          <p>{{ error }}</p>
          <button class="retry-button" @click="startCamera">Retry</button>
        </div>
        
        <div
          v-else
          class="camera-container"
          @pointerdown.capture="handleFramePointerDown"
          @touchstart.capture="handleFrameTouchStart"
          @mousedown.capture="handleFrameMouseDown"
          @click="handleFrameClick"
        >
          <video
            v-if="cameraMode === 'local'"
            ref="videoRef"
            autoplay
            playsinline
            class="camera-video"
            @pointerdown="handleFramePointerDown"
            @touchstart="handleFrameTouchStart"
            @mousedown="handleFrameMouseDown"
          ></video>
          <img
            v-else
            ref="streamImageRef"
            :src="piStreamUrl"
            alt="Raspberry Pi stream"
            class="camera-video"
            @load="onPiStreamLoaded"
            @error="onPiStreamError"
          />
          <canvas ref="canvasRef" style="display: none;"></canvas>
          <canvas ref="debugCanvasRef" class="debug-overlay"></canvas>
          
          <div class="camera-guide">
            <div
              ref="guideBoxRef"
              class="guide-box"
              :class="{ 'detected': objectDetected, 'processing': isBatchProcessing }"
            >
            </div>
            <div v-if="isCapturing" class="progress-bar-container">
              <div class="progress-bar"></div>
            </div>
            <p v-if="isBatchProcessing" class="status-message">Classifying {{ capturedBlobs.length }} item(s)...</p>
            <p v-else-if="statusMessage" class="status-message">{{ statusMessage }}</p>
            <p v-else-if="isCapturing">Capturing...</p>
            <p v-else>Position food item in the frame</p>
            <p v-if="capturedBlobs.length > 0 && !isBatchProcessing" class="items-count">{{ capturedBlobs.length }} item(s) captured</p>
          </div>
        </div>
      </div>
      
      <div class="camera-footer">
        <div v-if="canSwitchLocalCamera" class="camera-footer-top">
          <button
            class="switch-camera-button"
            @click="switchLocalCamera"
            aria-label="Switch camera"
            title="Switch camera"
            :disabled="!isCameraActive || isBatchProcessing || isSwitchingLocalCamera"
          >
            <span v-if="isSwitchingLocalCamera">...</span>
            <span v-else>&#8635;</span>
          </button>
        </div>
        <div class="camera-footer-actions">
          <button class="cancel-button" @click="close">Cancel</button>
          <button 
            class="finish-button" 
            @click="finishScanning"
            :disabled="!isCameraActive || isBatchProcessing"
          >
            <span v-if="isBatchProcessing">Classifying {{ capturedBlobs.length }} item(s)...</span>
            <span v-else>✓ Finish ({{ capturedBlobs.length }})</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.camera-popup-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.85);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.camera-popup-content {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  width: 90%;
  max-width: 700px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.camera-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid oklch(0.3 0 0);
}

.camera-header h2 {
  margin: 0;
  color: oklch(0.9 0 0);
  font-size: 1.5rem;
}

.close-button {
  background: none;
  border: none;
  color: oklch(0.7 0 0);
  font-size: 2rem;
  cursor: pointer;
  line-height: 1;
  padding: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-button:hover {
  color: oklch(0.9 0 0);
}

.camera-body {
  flex: 1;
  padding: 1.5rem;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  justify-content: center;
  align-items: center;
}


.camera-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  color: oklch(0.7 0 0);
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid oklch(0.3 0 0);
  border-top: 4px solid oklch(0.7 0.15 265);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.camera-error {
  text-align: center;
  color: oklch(0.7 0.15 30);
}

.camera-error p {
  margin-bottom: 1rem;
}

.retry-button {
  padding: 0.75rem 1.5rem;
  background-color: oklch(0.55 0.15 265);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}

.camera-container {
  position: relative;
  width: 100%;
  max-width: 640px;
  touch-action: manipulation;
}

.camera-video {
  width: 100%;
  height: auto;
  border-radius: 8px;
  display: block;
}

.debug-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  border-radius: 8px;
}

.camera-guide {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  text-align: center;
}

.guide-box {
  width: 300px;
  height: 300px;
  border: 3px dashed oklch(0.7 0.2 265);
  border-radius: 12px;
  margin: 0 auto 0.5rem;
  transition: border-color 0.3s ease, border-style 0.3s ease;
}

.guide-box.detected {
  border-color: oklch(0.7 0.2 145);
  animation: pulse 1.5s ease-in-out infinite;
}

.guide-box.processing {
  border-color: oklch(0.7 0.2 35);
  border-style: solid;
  animation: pulse-processing 1s ease-in-out infinite;
}

.progress-bar-container {
  width: 300px;
  height: 6px;
  background: oklch(0.2 0 0);
  border-radius: 3px;
  margin: 0 auto 1rem;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: oklch(0.7 0.2 145);
  border-radius: 3px;
  animation: fill-progress 1s linear forwards;
}

@keyframes fill-progress {
  from {
    width: 0%;
  }
  to {
    width: 100%;
  }
}

@keyframes pulse {
  0%, 100% { border-color: oklch(0.7 0.2 145); }
  50% { border-color: oklch(0.8 0.25 145); }
}

@keyframes pulse-processing {
  0%, 100% { border-color: oklch(0.7 0.2 35); }
  50% { border-color: oklch(0.8 0.25 35); }
}

@keyframes countdown-pulse {
  0% { transform: scale(1.2); opacity: 0; }
  50% { transform: scale(1); opacity: 1; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.camera-guide p {
  color: white;
  font-size: 1rem;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
  font-weight: 600;
  margin: 0.25rem 0;
}

.status-message {
  color: oklch(0.8 0.2 145);
  font-size: 1.1rem;
  font-weight: 700;
}

.items-count {
  color: oklch(0.7 0.15 265);
  font-size: 0.9rem;
}

.camera-footer {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  border-top: 1px solid oklch(0.3 0 0);
}

.camera-footer-top {
  display: flex;
  justify-content: center;
}

.camera-footer-actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.cancel-button,
.finish-button,
.switch-camera-button {
  flex: 1;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  font-weight: 600;
}

.cancel-button {
  background-color: oklch(0.3 0 0);
  color: oklch(0.8 0 0);
}

.cancel-button:hover {
  background-color: oklch(0.35 0 0);
}

.finish-button {
  background-color: oklch(0.65 0.2 145);
  color: white;
}

.switch-camera-button {
  background-color: transparent;
  color: white;
  flex: 0 0 auto;
  width: 3rem;
  min-width: 3rem;
  padding: 0.65rem;
  font-size: 1.4rem;
  line-height: 1;
}

.switch-camera-button:hover:not(:disabled) {
  background-color: oklch(0.35 0 0);
}

.finish-button:hover:not(:disabled) {
  background-color: oklch(0.7 0.22 145);
}

.finish-button:disabled,
.switch-camera-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .camera-popup-content {
    width: 95%;
    max-height: 95vh;
  }
  
  .camera-header {
    padding: 1rem;
  }
  
  .camera-body {
    padding: 1rem;
  }
  
  .guide-box {
    width: 200px;
    height: 200px;
  }
}
</style>
