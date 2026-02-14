<script setup>
import { ref, onMounted, watch } from 'vue'
import { searchRecipes, clearRecipeCache } from '../utils/recipeApi'

defineProps({
  msg: String,
})

const recipes = ref([])
const loading = ref(false)
const error = ref(null)

// Load saved filters from localStorage
const savedCuisine = localStorage.getItem('recipeFilter_cuisine') || ''
const savedType = localStorage.getItem('recipeFilter_type') || ''
const savedDiet = localStorage.getItem('recipeFilter_diet') || ''

// Filter state with saved values
const selectedCuisine = ref(savedCuisine)
const selectedType = ref(savedType)
const selectedDiet = ref(savedDiet)

// Save filters to localStorage whenever they change
watch(selectedCuisine, (newValue) => {
  localStorage.setItem('recipeFilter_cuisine', newValue)
})

watch(selectedType, (newValue) => {
  localStorage.setItem('recipeFilter_type', newValue)
})

watch(selectedDiet, (newValue) => {
  localStorage.setItem('recipeFilter_diet', newValue)
})

const cuisineOptions = [
  { value: '', label: 'All Cuisines' },
  { value: 'african', label: 'African' },
  { value: 'american', label: 'American' },
  { value: 'british', label: 'British' },
  { value: 'cajun', label: 'Cajun' },
  { value: 'caribbean', label: 'Caribbean' },
  { value: 'chinese', label: 'Chinese' },
  { value: 'eastern european', label: 'Eastern European' },
  { value: 'european', label: 'European' },
  { value: 'french', label: 'French' },
  { value: 'german', label: 'German' },
  { value: 'greek', label: 'Greek' },
  { value: 'indian', label: 'Indian' },
  { value: 'irish', label: 'Irish' },
  { value: 'italian', label: 'Italian' },
  { value: 'japanese', label: 'Japanese' },
  { value: 'jewish', label: 'Jewish' },
  { value: 'korean', label: 'Korean' },
  { value: 'latin american', label: 'Latin American' },
  { value: 'mediterranean', label: 'Mediterranean' },
  { value: 'mexican', label: 'Mexican' },
  { value: 'middle eastern', label: 'Middle Eastern' },
  { value: 'nordic', label: 'Nordic' },
  { value: 'southern', label: 'Southern' },
  { value: 'spanish', label: 'Spanish' },
  { value: 'thai', label: 'Thai' },
  { value: 'vietnamese', label: 'Vietnamese' }
]

const typeOptions = [
  { value: '', label: 'All Types' },
  { value: 'main course', label: 'Main Course' },
  { value: 'side dish', label: 'Side Dish' },
  { value: 'dessert', label: 'Dessert' },
  { value: 'appetizer', label: 'Appetizer' },
  { value: 'salad', label: 'Salad' },
  { value: 'bread', label: 'Bread' },
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'soup', label: 'Soup' },
  { value: 'beverage', label: 'Beverage' },
  { value: 'sauce', label: 'Sauce' },
  { value: 'snack', label: 'Snack' }
]

const dietOptions = [
  { value: '', label: 'All Diets' },
  { value: 'gluten free', label: 'Gluten Free' },
  { value: 'vegetarian', label: 'Vegetarian' },
  { value: 'vegan', label: 'Vegan' },
  { value: 'pescetarian', label: 'Pescetarian' },
  { value: 'low fodmap', label: 'Low FODMAP' }
]

const loadRecipes = async () => {
  loading.value = true
  error.value = null
  
  try {
    const result = await searchRecipes({
      cuisine: selectedCuisine.value,
      type: selectedType.value,
      diet: selectedDiet.value
    })
    
    // Handle result format: {error?, recipes}
    if (result.error) {
      error.value = result.error
    }
    recipes.value = result.recipes || []
    
    // Save recipes to localStorage for Home page to use
    localStorage.setItem('cachedRecipes', JSON.stringify(recipes.value))
  } catch (e) {
    error.value = e.message
    // Keep existing recipes on error
  } finally {
    loading.value = false
  }
}

const refreshRecipes = async () => {
  loading.value = true
  error.value = null
  
  try {
    // Clear cache first
    await clearRecipeCache()
    // Then load fresh recipes
    await loadRecipes()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const clearFilters = () => {
  selectedCuisine.value = ''
  selectedType.value = ''
  selectedDiet.value = ''
  // Filters are auto-saved by watchers, so just reload recipes
  loadRecipes()
}

onMounted(() => {
  loadRecipes()
})

const stripHtml = (html) => {
  const tmp = document.createElement('div')
  tmp.innerHTML = html
  return tmp.textContent || tmp.innerText || ''
}
</script>

<template>
  <div class="recipes-container">
    <div class="header">
      <h1>Recipe Suggestions</h1>
      <button @click="refreshRecipes" :disabled="loading" class="refresh-btn">
        {{ loading ? 'Loading...' : 'Refresh Recipes' }}
      </button>
    </div>
    
    <!-- Filters -->
    <div class="filters">
      <div class="filter-group">
        <label for="cuisine">Cuisine</label>
        <select id="cuisine" v-model="selectedCuisine" @change="loadRecipes">
          <option v-for="option in cuisineOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      
      <div class="filter-group">
        <label for="type">Meal Type</label>
        <select id="type" v-model="selectedType" @change="loadRecipes">
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      
      <div class="filter-group">
        <label for="diet">Diet</label>
        <select id="diet" v-model="selectedDiet" @change="loadRecipes">
          <option v-for="option in dietOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      
      <button @click="clearFilters" class="clear-filters-btn" :disabled="loading">
        Clear Filters
      </button>
    </div>
    
    <!-- Show error message even if we have cached recipes to display -->
    <div v-if="error && recipes.length > 0" class="warning-message">
      <p>⚠️ {{ error }}</p>
      <p class="warning-hint">Showing cached results. Click "Refresh Recipes" to try again.</p>
    </div>
    
    <div v-else-if="error" class="error-message">
      <p>❌ {{ error }}</p>
      <p v-if="error.includes('API key')" class="error-hint">
        To use recipe suggestions, you need to:
        <br>1. Sign up at <a href="https://spoonacular.com/food-api" target="_blank">spoonacular.com/food-api</a>
        <br>2. Get your free API key (150 requests/day)
        <br>3. Set it as an environment variable: SPOONACULAR_API_KEY
      </p>
      <p v-else-if="error.includes('quota')" class="error-hint">
        Your free tier allows 150 requests per day. The limit resets at midnight UTC.
      </p>
    </div>
    
    <div v-if="loading && recipes.length === 0" class="loading">
      <div class="spinner"></div>
      <p>Finding delicious recipes with your ingredients...</p>
    </div>
    
    <div v-else-if="!loading && recipes.length === 0" class="no-recipes">
      <p>🥘 No recipes found.</p>
      <p>Add ingredients to your inventory to get recipe suggestions!</p>
    </div>
    
    <div v-else class="recipe-grid">
      <div v-for="recipe in recipes" :key="recipe.id" class="recipe-card">
        <div class="recipe-content">
          <h3>{{ recipe.title }}</h3>
          
          <div class="recipe-meta">
            <span v-if="recipe.readyInMinutes" class="recipe-time">
              ⏱️ {{ recipe.readyInMinutes }} min
            </span>
            <span v-if="recipe.servings" class="servings">
              🍽️ {{ recipe.servings }} servings
            </span>
          </div>
          
          <div class="ingredients-match">
            <div class="match-item used">
              <span class="icon">✓</span>
              <span>{{ recipe.usedIngredientCount }} ingredient{{ recipe.usedIngredientCount !== 1 ? 's' : '' }} you have</span>
            </div>
            <div class="match-item missed">
              <span class="icon">+</span>
              <span>{{ recipe.missedIngredientCount }} ingredient{{ recipe.missedIngredientCount !== 1 ? 's' : '' }} needed</span>
            </div>
          </div>
          
          <div v-if="recipe.summary" class="recipe-summary">
            {{ stripHtml(recipe.summary).substring(0, 150) }}...
          </div>
          
          <a v-if="recipe.sourceUrl" :href="recipe.sourceUrl" target="_blank" class="view-recipe-btn">
            View Full Recipe →
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.recipes-container {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.header h1 {
  font-size: 2.5rem;
  color: oklch(0.9 0 0);
  margin: 0;
}

.refresh-btn {
  padding: 0.75rem 1.5rem;
  background-color: oklch(0.55 0.15 265);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.refresh-btn:hover:not(:disabled) {
  background-color: oklch(0.65 0.15 265);
  transform: translateY(-2px);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.filters {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 8px;
  flex-wrap: wrap;
  align-items: flex-end;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
  min-width: 180px;
}

.filter-group label {
  color: oklch(0.8 0 0);
  font-size: 0.9rem;
  font-weight: 600;
}

.filter-group select {
  padding: 0.75rem;
  background-color: oklch(0.15 0 0);
  color: oklch(0.9 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.filter-group select:hover {
  border-color: oklch(0.55 0.15 265);
}

.filter-group select:focus {
  outline: none;
  border-color: oklch(0.55 0.15 265);
  box-shadow: 0 0 0 3px rgba(138, 99, 210, 0.1);
}

.clear-filters-btn {
  padding: 0.75rem 1.5rem;
  background-color: oklch(0.3 0 0);
  color: oklch(0.8 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 6px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.3s ease;
  height: fit-content;
}

.clear-filters-btn:hover:not(:disabled) {
  background-color: oklch(0.35 0 0);
  border-color: oklch(0.5 0 0);
}

.clear-filters-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading {
  text-align: center;
  padding: 4rem 2rem;
  color: oklch(0.7 0 0);
}

.spinner {
  width: 50px;
  height: 50px;
  border: 4px solid oklch(0.3 0 0);
  border-top: 4px solid oklch(0.55 0.15 265);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.error-message {
  background-color: rgba(220, 38, 38, 0.1);
  border: 1px solid rgba(220, 38, 38, 0.3);
  border-radius: 8px;
  padding: 2rem;
  text-align: center;
  color: oklch(0.8 0 0);
}

.warning-message {
  background-color: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 8px;
  padding: 1.5rem;
  text-align: center;
  color: oklch(0.8 0 0);
  margin-bottom: 2rem;
}

.warning-hint {
  margin-top: 0.5rem;
  font-size: 0.9rem;
  color: oklch(0.7 0 0);
}

.error-hint {
  margin-top: 1rem;
  font-size: 0.9rem;
  color: oklch(0.7 0 0);
  line-height: 1.6;
}

.error-hint a {
  color: oklch(0.55 0.15 265);
  text-decoration: underline;
}

.no-recipes {
  text-align: center;
  padding: 4rem 2rem;
  color: oklch(0.6 0 0);
  font-size: 1.1rem;
}

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 2rem;
}

.recipe-card {
  background-color: oklch(0.2 0 0);
  border: 1px solid oklch(0.4 0 0);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.recipe-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
  border-color: oklch(0.55 0.15 265);
}

.recipe-content {
  padding: 1.5rem;
}

.recipe-content h3 {
  font-size: 1.3rem;
  color: oklch(0.9 0 0);
  margin: 0 0 1rem 0;
  line-height: 1.3;
}

.recipe-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  color: oklch(0.7 0 0);
  font-size: 0.9rem;
}

.recipe-time {
  font-weight: 600;
}

.ingredients-match {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.match-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
}

.match-item .icon {
  font-weight: bold;
  font-size: 1.1rem;
}

.match-item.used {
  color: #00FF00;
}

.match-item.missed {
  color: oklch(0.7 0 0);
}

.recipe-summary {
  color: oklch(0.7 0 0);
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 1rem;
}

.view-recipe-btn {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  background-color: oklch(0.55 0.15 265);
  color: white;
  text-decoration: none;
  border-radius: 6px;
  font-weight: 600;
  transition: all 0.3s ease;
  margin-top: 0.5rem;
}

.view-recipe-btn:hover {
  background-color: oklch(0.65 0.15 265);
  transform: translateX(4px);
}

@media (max-width: 768px) {
  .header h1 {
    font-size: 2rem;
  }
  
  .recipe-grid {
    grid-template-columns: 1fr;
  }
}
</style>
