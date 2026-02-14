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
      <div class="right-spacer"></div>
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
