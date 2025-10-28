<script setup>
import { ref } from 'vue'

defineProps({
  msg: String,
})

const count = ref(0)
</script>

<template>
  <h1>{{ msg }}</h1>

  <div class="card">
    <p>Filter Items</p>
    <button type="button" @click="count++">All</button>
    <button type="button" @click="count++">Expiring Soon</button>
    <button type="button" @click="count++">Expired</button>
  </div>
</template>

<style scoped>
.read-the-docs {
  color: #888;
}
</style>
