<!-- to run: "npm run dev" /> -->
<script setup>
import { RouterView, RouterLink } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import { SidebarProvider, SidebarTrigger } from './components/ui/sidebar'
</script>

<template>
  <SidebarProvider class="sidebar-provider">
    <AppSidebar />
    <div class="content-wrapper">
      <SidebarTrigger class="sidebar-trigger" />
      <main>
        <RouterView />
      </main>
    </div>
  </SidebarProvider>
</template>

<style scoped>
.sidebar-provider {
  height: 100vh;
  width: 100vw;
  display: flex;
}

.content-wrapper {
  display: flex;
  width: 100%;
  height: 100vh;
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
  padding: 0;
  text-align: left;
  overflow: auto;
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
</style>
