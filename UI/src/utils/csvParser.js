export async function loadFoodsFromCSV() {
  try {
    // Add timestamp to bust cache and get fresh data
    const response = await fetch(`/foods.csv?t=${Date.now()}`)
    const csvText = await response.text()
    const lines = csvText.trim().split('\n').filter(line => line.trim() !== '')
    
    // Skip header row
    const foods = lines.slice(1).map(line => {
      const [id, name, freshnessScore, daysUntilSpoilage, timeInFridge, foodGroup] = line.split(',')
      return {
        id: parseInt(id),
        name: name.trim(),
        freshnessScore: parseInt(freshnessScore),
        daysUntilSpoilage: parseInt(daysUntilSpoilage),
        timeInFridge: timeInFridge.trim(),
        foodGroup: foodGroup.trim()
      }
    })
    
    return foods
  } catch (error) {
    console.error('Error loading foods from CSV:', error)
    return []
  }
}
