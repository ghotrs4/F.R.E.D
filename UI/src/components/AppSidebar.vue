<script setup>
import { Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from './ui/sidebar'
import { Home, Package } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'

const props = defineProps({
  geminiEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['toggle-gemini'])

const handleGeminiToggle = (event) => {
  emit('toggle-gemini', event.target.checked)
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
</style>
