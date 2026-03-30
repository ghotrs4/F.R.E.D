<script setup>
import { ref } from 'vue'
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from './ui/sidebar'
import { Home, Package } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { calibrateMqSensors } from '../utils/sensorApi'

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

const handleLocalCameraToggle = (event) => {
  emit('toggle-local-camera', event.target.checked)
}

const handleGeminiToggle = (event) => {
  emit('toggle-gemini', event.target.checked)
}

const calibratingMq = ref(false)
const calibrationStatus = ref('')

const handleCalibrateMq = async () => {
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
      </div>
    </SidebarContent>
  </Sidebar>
</template>

<style scoped>
.sidebar-footer {
  margin-top: auto;
  padding: 0.9rem 0.75rem 1rem;
  border-top: 1px solid oklch(0.3 0 0);
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
</style>
