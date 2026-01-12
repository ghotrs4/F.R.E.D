import { createWebHistory, createRouter } from 'vue-router'
import Home from './components/Home.vue'
import Inventory from './components/Inventory.vue'
import Stats from './components/Stats.vue'
import Recipes from './components/Recipes.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/inventory', component: Inventory },
  { path: '/stats', component: Stats },
  { path: '/recipes', component: Recipes },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
