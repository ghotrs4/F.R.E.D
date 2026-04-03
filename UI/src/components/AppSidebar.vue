<script setup>
import { ref } from 'vue'
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from './ui/sidebar'
import { Home, Package } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { calibrateMqSensors } from '../utils/sensorApi'

const DEV_SETTINGS_PASSWORD = (import.meta.env.VITE_DEV_SETTINGS_PASSWORD || 'fred-dev').trim()

const props = defineProps({
  useLocalCamera: {
    type: Boolean,
    default: false
  },
  geminiEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['toggle-gemini', 'toggle-local-camera'])

const developerAuthMessage = ref('')
const showPasswordModal = ref(false)
const pendingPasswordAction = ref(null)
const passwordInput = ref('')
let pendingAuthCallback = null

const requestDeveloperPassword = (actionLabel) => {
  return new Promise((resolve) => {
    pendingPasswordAction.value = actionLabel
    passwordInput.value = ''
    developerAuthMessage.value = ''
    showPasswordModal.value = true
    pendingAuthCallback = resolve
  })
}

const submitPasswordModal = () => {
  const enteredPassword = passwordInput.value.trim()

  if (!enteredPassword) {
    developerAuthMessage.value = 'Password cannot be empty.'
    return
  }

  if (enteredPassword !== DEV_SETTINGS_PASSWORD) {
    developerAuthMessage.value = 'Incorrect password.'
    passwordInput.value = ''
    return
  }

  developerAuthMessage.value = ''
  showPasswordModal.value = false
  passwordInput.value = ''

  if (pendingAuthCallback) {
    pendingAuthCallback(true)
    pendingAuthCallback = null
  }
}

const cancelPasswordModal = () => {
  developerAuthMessage.value = ''
  showPasswordModal.value = false
  passwordInput.value = ''

  if (pendingAuthCallback) {
    pendingAuthCallback(false)
    pendingAuthCallback = null
  }
}

const handlePasswordModalKeydown = (event) => {
  if (event.key === 'Enter') {
    submitPasswordModal()
  } else if (event.key === 'Escape') {
    cancelPasswordModal()
  }
}

const handleLocalCameraToggle = async (event) => {
  const requestedValue = event.target.checked
  const authed = await requestDeveloperPassword('change camera source')
  if (!authed) {
    event.target.checked = props.useLocalCamera
    return
  }
  emit('toggle-local-camera', requestedValue)
}

const handleGeminiToggle = async (event) => {
  const requestedValue = event.target.checked
  const authed = await requestDeveloperPassword('toggle Gemini requests')
  if (!authed) {
    event.target.checked = props.geminiEnabled
    return
  }
  emit('toggle-gemini', requestedValue)
}

const calibratingMq = ref(false)
const calibrationStatus = ref('')

const handleCalibrateMq = async () => {
  const authed = await requestDeveloperPassword('recalibrate MQ sensors')
  if (!authed) return
  calibratingMq.value = true
  calibrationStatus.value = ''
  try {
    const result = await calibrateMqSensors()
    const updatedCount = Object.keys(result?.updatedMaxValues || {}).length
    calibrationStatus.value = `Calibrated ${updatedCount} MQ sensors.`
  } catch (error) {
    calibrationStatus.value = `Calibration failed: ${error.message}`
  } finally {
    calibratingMq.value = false
  }
}
</script>

<template>
  <Sidebar>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupLabel>F.R.E.D</SidebarGroupLabel>
        <SidebarGroupContent>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton as-child>
                <RouterLink to="/">
                  <Home />
                  <span>Home</span>
                </RouterLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child>
                <RouterLink to="/inventory">
                  <Package />
                  <span>Inventory</span>
                </RouterLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child>
                <RouterLink to="/stats">
                  <Package />
                  <span>Stats</span>
                </RouterLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton as-child>
                <RouterLink to="/recipes">
                  <Package />
                  <span>Recipes</span>
                </RouterLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <div class="sidebar-footer">
        <h4 class="developer-title">Developer Settings</h4>

        <label class="gemini-toggle">
          <span class="toggle-label">Use Local Camera</span>
          <input
            type="checkbox"
            class="toggle-input"
            :checked="props.useLocalCamera"
            @change="handleLocalCameraToggle"
          />
        </label>
        <p class="toggle-hint">
          Off uses Raspberry Pi camera stream; on uses this device's camera.
        </p>

        <label class="gemini-toggle">
          <span class="toggle-label">Gemini Requests</span>
          <input
            type="checkbox"
            class="toggle-input"
            :checked="props.geminiEnabled"
            @change="handleGeminiToggle"
          />
        </label>
        <p class="toggle-hint">
          Turn on to use Gemini for food classification; turn off to use local ResNet18 instead.
        </p>

        <button
          type="button"
          class="calibrate-button"
          :disabled="calibratingMq"
          @click="handleCalibrateMq"
        >
          {{ calibratingMq ? 'Calibrating MQ...' : 'Calibrate MQ Sensors' }}
        </button>
        <p v-if="calibrationStatus" class="toggle-hint calibration-hint">
          {{ calibrationStatus }}
        </p>
        <p v-if="developerAuthMessage" class="toggle-hint dev-auth-message">{{ developerAuthMessage }}</p>
      </div>
    </SidebarContent>
  </Sidebar>

  <!-- Developer Password Modal -->
  <div v-if="showPasswordModal" class="password-modal-overlay" @click.self="cancelPasswordModal">
    <div class="password-modal">
      <h3>Developer Settings</h3>
      <p class="modal-prompt">Enter password to {{ pendingPasswordAction }}:</p>
      <input
        v-model="passwordInput"
        type="password"
        class="modal-password-input"
        placeholder="Password"
        @keydown="handlePasswordModalKeydown"
        autofocus
      />
      <p v-if="developerAuthMessage" class="modal-auth-message">{{ developerAuthMessage }}</p>
      <div class="modal-buttons">
        <button class="modal-cancel-btn" @click="cancelPasswordModal">Cancel</button>
        <button class="modal-submit-btn" @click="submitPasswordModal">Submit</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar-footer {
  margin-top: auto;
  padding: 0.9rem 0.75rem 1rem;
  border-top: 1px solid oklch(0.3 0 0);
}

.developer-title {
  margin: 0 0 0.75rem;
  font-size: 0.83rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: oklch(0.86 0 0);
}

.dev-auth-message {
  color: oklch(0.72 0.14 25);
  margin-top: 0.55rem;
}

.gemini-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.toggle-label {
  font-size: 0.9rem;
  font-weight: 600;
}

.toggle-input {
  width: 2.6rem;
  height: 1.4rem;
  accent-color: oklch(0.65 0.18 150);
  cursor: pointer;
}

.toggle-hint {
  margin: 0.45rem 0 0;
  font-size: 0.75rem;
  color: oklch(0.76 0 0);
  line-height: 1.25;
}

.calibrate-button {
  width: 100%;
  margin-top: 0.85rem;
  border: 1px solid oklch(0.62 0.13 150);
  border-radius: 0.45rem;
  background: oklch(0.38 0.08 150);
  color: oklch(0.97 0 0);
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.5rem 0.65rem;
  cursor: pointer;
}

.calibrate-button:hover:enabled {
  background: oklch(0.44 0.09 150);
}

.calibrate-button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.calibration-hint {
  margin-top: 0.55rem;
}

.password-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.password-modal {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  padding: 1.5rem;
  max-width: 400px;
  width: 85vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
}

.password-modal h3 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
  color: oklch(0.9 0 0);
}

.modal-prompt {
  margin: 0 0 1rem;
  font-size: 0.95rem;
  color: oklch(0.8 0 0);
}

.modal-password-input {
  width: 100%;
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  background: oklch(0.15 0 0);
  color: oklch(0.96 0 0);
  padding: 0.75rem;
  font-size: 1rem;
  margin-bottom: 1rem;
  box-sizing: border-box;
}

.modal-password-input:focus {
  outline: none;
  border-color: oklch(0.65 0.18 150);
  background: oklch(0.18 0 0);
}

.modal-auth-message {
  margin: 0 0 1rem;
  font-size: 0.85rem;
  color: oklch(0.72 0.14 25);
}

.modal-buttons {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.modal-cancel-btn,
.modal-submit-btn {
  padding: 0.65rem 1.25rem;
  border: 1px solid oklch(0.35 0 0);
  border-radius: 6px;
  background: oklch(0.25 0 0);
  color: oklch(0.9 0 0);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.modal-cancel-btn:hover {
  background: oklch(0.3 0 0);
}

.modal-submit-btn {
  background: oklch(0.45 0.12 150);
  border-color: oklch(0.5 0.15 150);
}

.modal-submit-btn:hover {
  background: oklch(0.5 0.14 150);
}
</style>
