<!--

-->

<script setup>
import { ref, shallowRef, onMounted, onUnmounted } from 'vue'
import { ObjectDetector, FilesetResolver } from '@mediapipe/tasks-vision'

const emit = defineEmits(['close', 'finish', 'classifying'])

const videoRef = ref(null)
const canvasRef = ref(null)
const stream = ref(null)
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
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? '' : `http://${window.location.hostname}:5000`)
).replace(/\/$/, '')
const captureCooldown = ref(false)
const debugCanvasRef = ref(null)
const showDebugOverlay = ref(false)

const toggleDebugOverlay = () => {
  showDebugOverlay.value = !showDebugOverlay.value
  // Clear canvas immediately when turning off
  if (!showDebugOverlay.value) {
    const debugCanvas = debugCanvasRef.value
    if (debugCanvas) {
      debugCanvas.getContext('2d').clearRect(0, 0, debugCanvas.width, debugCanvas.height)
    }
  }
}

const startCamera = async () => {
  try {
    stream.value = await navigator.mediaDevices.getUserMedia({ 
      video: { 
        facingMode: 'environment',
        width: { ideal: 1280 },
        height: { ideal: 720 }
      } 
    })
    if (videoRef.value) {
      videoRef.value.srcObject = stream.value
      isCameraActive.value = true
      startDetection()
    }
  } catch (e) {
    error.value = 'Failed to access camera. Please ensure camera permissions are granted.'
    console.error('Camera error:', e)
  }
}

const stopCamera = () => {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
    isCameraActive.value = false
  }
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
  if (!videoRef.value || !canvasRef.value || isBatchProcessing.value) return
  
  const video = videoRef.value
  const canvas = canvasRef.value
  const context = canvas.getContext('2d')
  
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  
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
    capturedBlobs.value.forEach((blob, i) => {
      formData.append(`image_${i}`, blob, `capture_${i}.jpg`)
    })
    
    const response = await fetch(`${API_BASE_URL}/api/classify-food/batch`, {
      method: 'POST',
      body: formData
    })
    
    const results = []
    if (response.ok) {
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
    }

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
  
  console.log('Starting detection...')
  
  detectionInterval.value = setInterval(() => {
    if (!videoRef.value || videoRef.value.readyState !== 4) {
      return
    }
    
    try {
      const raw = model.value.detectForVideo(videoRef.value, performance.now())
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
      
      // Get video dimensions
      const videoWidth = videoRef.value.videoWidth
      const videoHeight = videoRef.value.videoHeight
      
      // Calculate guide box boundaries in video coordinates
      // Guide box is 300x300px centered on the display, but we need to map to actual video size
      const displayWidth = videoRef.value.clientWidth
      const displayHeight = videoRef.value.clientHeight
      
      // Scale factor from display to video
      const scaleX = videoWidth / displayWidth
      const scaleY = videoHeight / displayHeight
      
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
  // Load MediaPipe EfficientDet model (all assets served locally)
  try {
    const vision = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
    model.value = await ObjectDetector.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: '/mediapipe/efficientdet_lite0.tflite',
        delegate: 'GPU'
      },
      scoreThreshold: 0.1,
      runningMode: 'VIDEO',
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
        
        <div v-else class="camera-container">
          <video 
            ref="videoRef" 
            autoplay 
            playsinline
            class="camera-video"
          ></video>
          <canvas ref="canvasRef" style="display: none;"></canvas>
          <canvas ref="debugCanvasRef" class="debug-overlay"></canvas>
          
          <div class="camera-guide">
            <div class="guide-box" :class="{ 'detected': objectDetected, 'processing': isProcessing }">
            </div>
            <div v-if="isCapturing" class="progress-bar-container">
              <div class="progress-bar"></div>
            </div>
            <p v-if="isBatchProcessing" class="status-message">Classifying {{ capturedBlobs.length }} item(s)...</p>
            <p v-else-if="statusMessage" class="status-message">{{ statusMessage }}</p>
            <p v-else-if="isCapturing">Capturing...</p>
            <p v-else>{{ objectDetected ? 'Object detected!' : 'Position food item in the frame' }}</p>
            <p v-if="capturedBlobs.length > 0 && !isBatchProcessing" class="items-count">{{ capturedBlobs.length }} item(s) captured</p>
          </div>
        </div>
      </div>
      
      <div class="camera-footer">
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
  justify-content: space-between;
  gap: 1rem;
  padding: 1.5rem;
  border-top: 1px solid oklch(0.3 0 0);
}

.cancel-button,
.finish-button {
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

.finish-button:hover:not(:disabled) {
  background-color: oklch(0.7 0.22 145);
}

.finish-button:disabled {
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
