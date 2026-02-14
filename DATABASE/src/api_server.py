from flask import Flask, jsonify, request
from flask_cors import CORS
import csv
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from spoilage_algorithm import predict_spoilage
from sensor_interface import get_sensor

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend connection

# Spoonacular API configuration
SPOONACULAR_API_KEY = os.environ.get('SPOONACULAR_API_KEY')

# Path to the CSV database
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'database.csv')

# Recipe cache to avoid excessive API calls
# Cache persists until manually cleared by user clicking 'Refresh Results'
recipe_cache = {
    'data': None,
    'timestamp': None,
    'cache_key': None,
    'backup': None,  # Backup cache for failed refresh attempts
    'offset': 0  # Track offset for fetching new recipes on refresh
}

def read_foods():
    """Read all foods from the CSV database and calculate real-time freshness"""
    foods = []
    sensor = get_sensor()
    current_temp = sensor.get_temperature()
    current_humidity = sensor.get_humidity()
    
    try:
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Parse dates - use entry_date as purchase_date
                try:
                    entry_date = datetime.fromisoformat(row['entry_date']) if row['entry_date'] else datetime.now()
                except:
                    entry_date = datetime.now()
                
                try:
                    expiration_date = datetime.fromisoformat(row['expiration_date']) if row['expiration_date'] else None
                except:
                    expiration_date = None
                
                # Get cumulative temperature abuse
                cumulative_temp_abuse = float(row['cumulative_temp_abuse']) if row['cumulative_temp_abuse'] else 0.0
                
                # Calculate real-time spoilage prediction
                prediction = predict_spoilage(
                    food_category=row['food_category'] if row['food_category'] else 'other',
                    purchase_date=entry_date,  # Use entry_date as purchase_date
                    current_temp=current_temp,
                    current_humidity=current_humidity,
                    packaging_type=row['packaging_type'] if row['packaging_type'] else 'sealed',
                    cumulative_temp_abuse=cumulative_temp_abuse,
                    expiration_date=expiration_date,
                    food_name=row['food_name'] if row['food_name'] else '',
                    storage_location=row.get('storage_location', 'regular')
                )
                
                # Transform CSV data to match frontend format with real-time calculations
                food = {
                    'id': row['item_id'],
                    'name': row['food_name'],
                    'freshnessScore': prediction['freshness_score'],
                    'daysUntilSpoilage': int(prediction['days_until_spoilage']),
                    'timeInFridge': calculate_time_in_fridge(row['entry_date']),
                    'foodGroup': row['food_category'].lower() if row['food_category'] else 'other',
                    'packagingType': row['packaging_type'] if row['packaging_type'] else '',
                    'expirationDate': row['expiration_date'] if row['expiration_date'] else '',
                    'storageLocation': row.get('storage_location', 'regular'),
                    'cumulativeTempAbuse': cumulative_temp_abuse,
                    'safetyCategory': prediction['safety_category'],
                    'warnings': prediction.get('warnings', [])
                }
                foods.append(food)
    except Exception as e:
        print(f"Error reading database: {e}")
    return foods

def calculate_time_in_fridge(entry_date):
    """Calculate how long the item has been in the fridge"""
    if not entry_date:
        return '0 days'
    try:
        entry = datetime.fromisoformat(entry_date.replace('Z', '+00:00'))
        now = datetime.now()
        days = (now - entry).days
        if days == 0:
            hours = (now - entry).seconds // 3600
            return f"{hours} hours" if hours != 1 else "1 hour"
        return f"{days} days" if days != 1 else "1 day"
    except:
        return '0 days'

def log_temperature_reading(temperature, humidity):
    """Log temperature and humidity reading with timestamp"""
    try:
        temp_history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'temperature_history.csv')
        
        # Get current timestamp
        timestamp = datetime.now().isoformat()
        
        # Append to CSV
        with open(temp_history_path, 'a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['timestamp', 'temperature', 'humidity'])
            writer.writerow({
                'timestamp': timestamp,
                'temperature': round(temperature, 2),
                'humidity': round(humidity, 2)
            })
        
        # Clean up old data (keep only last 12 hours)
        twelve_hours_ago = datetime.now() - timedelta(hours=12)
        recent_readings = []
        
        with open(temp_history_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    reading_time = datetime.fromisoformat(row['timestamp'])
                    if reading_time >= twelve_hours_ago:
                        recent_readings.append(row)
                except:
                    pass
        
        # Write back only recent readings
        with open(temp_history_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['timestamp', 'temperature', 'humidity'])
            writer.writeheader()
            writer.writerows(recent_readings)
            
    except Exception as e:
        print(f"Error logging temperature: {e}")

def write_foods(foods):
    """Write foods back to the CSV database"""
    try:
        # Read existing data to preserve all fields
        existing_data = {}
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            for row in reader:
                existing_data[row['item_id']] = row
        
        # Update or add new foods
        for food in foods:
            item_id = food['id']
            if item_id in existing_data:
                # Update existing item
                existing_data[item_id]['food_name'] = food['name']
                existing_data[item_id]['freshness_score'] = str(food['freshnessScore'])
                existing_data[item_id]['days_until_spoilage'] = str(food['daysUntilSpoilage'])
                existing_data[item_id]['safety_category'] = food.get('safetyCategory', 'Fresh')
                existing_data[item_id]['food_category'] = food['foodGroup'].capitalize()
                if 'packagingType' in food:
                    existing_data[item_id]['packaging_type'] = food['packagingType']
                if 'expirationDate' in food:
                    existing_data[item_id]['expiration_date'] = food['expirationDate']
                if 'storageLocation' in food:
                    existing_data[item_id]['storage_location'] = food['storageLocation']
            else:
                # Create new item
                days_in_fridge = food.get('daysInFridge', 0)
                entry_date = datetime.now() - timedelta(days=days_in_fridge)
                existing_data[item_id] = {
                    'item_id': item_id,
                    'food_name': food['name'],
                    'food_category': food['foodGroup'].capitalize(),
                    'entry_date': entry_date.isoformat(),
                    'expiration_date': food.get('expirationDate', ''),
                    'temp_at_entry': '4.5',
                    'humidity_at_entry': '85.0',
                    'packaging_type': food.get('packagingType', 'sealed'),
                    'storage_location': food.get('storageLocation', 'regular'),
                    'cumulative_temp_abuse': '0.0',
                    'freshness_score': str(food['freshnessScore']),
                    'days_until_spoilage': str(food['daysUntilSpoilage']),
                    'safety_category': 'Fresh'
                }
        
        # Write back to CSV
        with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in existing_data.values():
                writer.writerow(row)
        
        return True
    except Exception as e:
        print(f"Error writing database: {e}")
        return False

# API Routes

@app.route('/api/foods', methods=['GET'])
def get_foods():
    """Get all foods"""
    foods = read_foods()
    return jsonify(foods)

@app.route('/api/foods/<item_id>', methods=['GET'])
def get_food(item_id):
    """Get a specific food by ID"""
    foods = read_foods()
    food = next((f for f in foods if f['id'] == item_id), None)
    if food:
        return jsonify(food)
    return jsonify({'error': 'Food not found'}), 404

@app.route('/api/foods', methods=['POST'])
def create_food():
    """Create a new food item"""
    data = request.json
    
    # Generate new ID
    foods = read_foods()
    max_id = 0
    for food in foods:
        try:
            num = int(food['id'].split('_')[1])
            max_id = max(max_id, num)
        except:
            pass
    
    new_food = {
        'id': f'ITEM_{str(max_id + 1).zfill(3)}',
        'name': data.get('name', 'Unknown'),
        'freshnessScore': data.get('freshnessScore', 100),
        'daysUntilSpoilage': data.get('daysUntilSpoilage', 7),
        'timeInFridge': '0 days',
        'foodGroup': data.get('foodGroup', 'other'),
        'packagingType': data.get('packagingType', 'sealed'),
        'expirationDate': data.get('expirationDate', ''),
        'storageLocation': data.get('storageLocation', 'regular'),
        'daysInFridge': data.get('daysInFridge', 0)
    }
    
    foods.append(new_food)
    if write_foods(foods):
        return jsonify(new_food), 201
    return jsonify({'error': 'Failed to create food'}), 500

@app.route('/api/foods/<item_id>', methods=['PUT'])
def update_food(item_id):
    """Update an existing food item"""
    data = request.json
    foods = read_foods()
    
    for i, food in enumerate(foods):
        if food['id'] == item_id:
            foods[i] = {
                'id': item_id,
                'name': data.get('name', food['name']),
                'freshnessScore': data.get('freshnessScore', food['freshnessScore']),
                'daysUntilSpoilage': data.get('daysUntilSpoilage', food['daysUntilSpoilage']),
                'timeInFridge': food['timeInFridge'],
                'foodGroup': data.get('foodGroup', food['foodGroup']),
                'packagingType': data.get('packagingType', food.get('packagingType', '')),
                'expirationDate': data.get('expirationDate', food.get('expirationDate', '')),
                'storageLocation': data.get('storageLocation', food.get('storageLocation', 'regular'))
            }
            if write_foods(foods):
                return jsonify(foods[i])
            return jsonify({'error': 'Failed to update food'}), 500
    
    return jsonify({'error': 'Food not found'}), 404

@app.route('/api/foods/<item_id>', methods=['DELETE'])
def delete_food(item_id):
    """Delete a food item"""
    try:
        # Read all data
        rows = []
        with open(DB_PATH, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            for row in reader:
                if row['item_id'] != item_id:
                    rows.append(row)
        
        # Write back without the deleted item
        with open(DB_PATH, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return jsonify({'message': 'Food deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensor', methods=['GET'])
def get_sensor_data():
    """Get current sensor readings (temperature and humidity)"""
    sensor = get_sensor()
    temperature = sensor.get_temperature()
    humidity = sensor.get_humidity()
    connected = sensor.is_connected()
    
    # Log temperature reading if sensors are connected
    if connected:
        log_temperature_reading(temperature, humidity)
    
    return jsonify({
        'temperature': temperature,
        'humidity': humidity,
        'connected': connected
    })

@app.route('/api/stats/outcome', methods=['POST'])
def record_outcome():
    """Record the outcome of a food item (consumed, wasted)"""
    data = request.json
    item_id = data.get('item_id')
    outcome = data.get('outcome')  # 'consumed', 'wasted'
    
    if not item_id or not outcome or outcome not in ['consumed', 'wasted']:
        return jsonify({'error': 'Invalid data'}), 400
    
    try:
        # Get food details before deletion
        foods = read_foods()
        food = next((f for f in foods if f['id'] == item_id), None)
        
        if not food:
            return jsonify({'error': 'Food not found'}), 404
        
        # Calculate days tracked
        try:
            entry_date = datetime.now()  # Default to now if can't parse
            days_tracked = (datetime.now() - entry_date).days
        except:
            days_tracked = 0
        
        # Record outcome
        outcome_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_outcomes.csv')
        with open(outcome_path, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                item_id,
                food['name'],
                outcome,
                datetime.now().isoformat(),
                food['freshnessScore'],
                days_tracked
            ])
        
        # Update daily stats
        update_daily_stats()
        
        return jsonify({'message': 'Outcome recorded successfully'})
    except Exception as e:
        print(f"Error recording outcome: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/history', methods=['GET'])
def get_waste_history():
    """Get historical waste statistics"""
    try:
        history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'waste_history.csv')
        history = []
        
        with open(history_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                history.append({
                    'date': row['date'],
                    'itemsConsumed': int(row['items_consumed']),
                    'itemsWasted': int(row['items_wasted']),
                    'totalItems': int(row['total_items']),
                    'wastePercentage': float(row['waste_percentage'])
                })
        
        return jsonify(history[-7:])  # Return last 7 days
    except Exception as e:
        print(f"Error reading history: {e}")
        return jsonify([])

def update_daily_stats():
    """Update daily waste statistics and clean up old data"""
    try:
        today = datetime.now().date()
        today_str = today.isoformat()
        seven_days_ago = (today - timedelta(days=7)).isoformat()
        
        outcome_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'item_outcomes.csv')
        history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'waste_history.csv')
        
        # Read and filter item_outcomes to keep only last 7 days
        recent_outcomes = []
        consumed = 0
        wasted = 0
        
        with open(outcome_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            for row in reader:
                outcome_date = row['outcome_date'][:10]  # Get just the date part
                
                # Keep only records from last 7 days
                if outcome_date >= seven_days_ago:
                    recent_outcomes.append(row)
                    
                    # Count today's outcomes
                    if outcome_date == today_str:
                        if row['outcome'] == 'consumed':
                            consumed += 1
                        elif row['outcome'] == 'wasted':
                            wasted += 1
        
        # Write back only recent outcomes
        with open(outcome_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recent_outcomes)
        # Write back only recent outcomes
        with open(outcome_path, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(recent_outcomes)
        
        total = consumed + wasted
        waste_pct = (wasted / total * 100) if total > 0 else 0
        
        # Read existing history and keep only last 7 days
        history_data = []
        try:
            with open(history_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                history_data = [row for row in reader if row['date'] >= seven_days_ago and row['date'] != today_str]
        except:
            pass
        
        # Add/update today's entry
        history_data.append({
            'date': today_str,
            'items_consumed': consumed,
            'items_wasted': wasted,
            'total_items': total,
            'waste_percentage': round(waste_pct, 2)
        })
        
        # Write back only last 7 days
        with open(history_path, 'w', newline='', encoding='utf-8') as file:
            fieldnames = ['date', 'items_consumed', 'items_wasted', 'total_items', 'waste_percentage']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(history_data)
            
    except Exception as e:
        print(f"Error updating daily stats: {e}")

@app.route('/api/stats/temperature', methods=['GET'])
def get_temperature_history():
    """Get temperature history for the last 12 hours"""
    try:
        temp_history_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'temperature_history.csv')
        history = []
        
        with open(temp_history_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                history.append({
                    'timestamp': row['timestamp'],
                    'temperature': float(row['temperature']),
                    'humidity': float(row['humidity'])
                })
        
        return jsonify(history)
    except Exception as e:
        print(f"Error reading temperature history: {e}")
        return jsonify([])

@app.route('/api/recipes/cache/clear', methods=['POST'])
def clear_recipe_cache():
    """Clear the recipe cache to force fresh API calls, but keep backup"""
    # Save current cache as backup in case new fetch fails
    recipe_cache['backup'] = recipe_cache['data']
    recipe_cache['data'] = None
    recipe_cache['timestamp'] = None
    recipe_cache['cache_key'] = None
    # Increment offset to get different recipes on next fetch
    recipe_cache['offset'] = recipe_cache.get('offset', 0) + 6
    return jsonify({'message': 'Recipe cache cleared'})

@app.route('/api/recipes/search', methods=['GET'])
def search_recipes():
    """Search recipes based on available ingredients using Spoonacular API"""
    try:
        # Get optional filters from query parameters
        cuisine = request.args.get('cuisine', '')
        meal_type = request.args.get('type', '')
        diet = request.args.get('diet', '')
        
        foods = read_foods()
        
        if not foods:
            return jsonify([])
        
        # Sort by days until spoilage to prioritize expiring items
        sorted_foods = sorted(foods, key=lambda x: x['daysUntilSpoilage'])
        
        # Get ingredient names (use top 10 to avoid overly restrictive searches)
        ingredient_names = [food['name'] for food in sorted_foods[:10]]
        ingredients_str = ','.join(ingredient_names)
        
        # Create cache key based on filters AND current inventory
        # This ensures cache is invalidated when inventory changes
        cache_key = f"{cuisine}|{meal_type}|{diet}|{ingredients_str}"
        
        # Check cache first - cache persists until manually cleared or inventory changes
        # Use 'is not None' to allow caching of empty lists and error objects
        if recipe_cache['data'] is not None and recipe_cache.get('cache_key') == cache_key:
            cache_age = (datetime.now() - recipe_cache['timestamp']).total_seconds() if recipe_cache['timestamp'] else 0
            print(f"✓ Using cached recipes (age: {int(cache_age)}s)")
            return jsonify(recipe_cache['data'])
        
        # Get current offset for fetching different recipes
        current_offset = recipe_cache.get('offset', 0)
        print(f"⚠ Making Spoonacular API calls ({cuisine or 'all'}/{meal_type or 'all'}/{diet or 'all'}) - offset: {current_offset}")
        
        # Call Spoonacular API - Find by Ingredients
        url = 'https://api.spoonacular.com/recipes/findByIngredients'
        params = {
            'apiKey': SPOONACULAR_API_KEY,
            'ingredients': ingredients_str,
            'number': 6,  # Return 6 recipes
            'offset': current_offset,  # Offset for pagination
            'ranking': 2,  # Maximize used ingredients
            'ignorePantry': False
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 401:
            error_response = {'error': 'Invalid API key. Please set SPOONACULAR_API_KEY environment variable.'}
            # Cache the error so we don't keep retrying
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 401
        
        if response.status_code == 402:
            error_response = {'error': 'Reached daily recipe generation quota. Try again tomorrow or upgrade your Spoonacular API plan.'}
            # Cache the error so we don't keep hitting the quota limit
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 402
        
        if not response.ok:
            error_response = {'error': f'Spoonacular API error: {response.status_code}'}
            # Cache the error
            recipe_cache['data'] = error_response
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            return jsonify(error_response), 500
        
        recipes = response.json()
        
        # Filter out recipes that don't use any of our ingredients
        recipes = [r for r in recipes if r.get('usedIngredientCount', 0) > 0]
        
        if not recipes:
            # Cache empty result so we don't keep making API calls
            # Reset offset back to 0 since we've exhausted available recipes
            recipe_cache['data'] = []
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            recipe_cache['backup'] = None
            recipe_cache['offset'] = 0
            print("✓ Cached empty recipe result (no more recipes available)")
            return jsonify([])
        
        # Enrich with recipe details (instructions, time, servings, etc.)
        detailed_recipes = []
        for recipe in recipes:
            detail_url = f"https://api.spoonacular.com/recipes/{recipe['id']}/information"
            detail_params = {'apiKey': SPOONACULAR_API_KEY}
            
            try:
                detail_response = requests.get(detail_url, params=detail_params, timeout=10)
                if detail_response.ok:
                    recipe_detail = detail_response.json()
                    
                    # Apply filters on detailed recipe data
                    # Filter by cuisine
                    if cuisine:
                        cuisines = [c.lower() for c in recipe_detail.get('cuisines', [])]
                        if cuisine.lower() not in cuisines:
                            continue
                    
                    # Filter by meal type
                    if meal_type:
                        dish_types = [d.lower() for d in recipe_detail.get('dishTypes', [])]
                        if meal_type.lower() not in dish_types:
                            continue
                    
                    # Filter by diet
                    if diet:
                        diets = [d.lower() for d in recipe_detail.get('diets', [])]
                        if diet.lower() not in diets:
                            continue
                    
                    # Combine basic info with detailed info
                    detailed_recipe = {
                        'id': recipe['id'],
                        'title': recipe['title'],
                        # 'image': recipe['image'],
                        'usedIngredientCount': recipe['usedIngredientCount'],
                        'missedIngredientCount': recipe['missedIngredientCount'],
                        'usedIngredients': recipe.get('usedIngredients', []),
                        'missedIngredients': recipe.get('missedIngredients', []),
                        'readyInMinutes': recipe_detail.get('readyInMinutes', 'N/A'),
                        'servings': recipe_detail.get('servings', 'N/A'),
                        'sourceUrl': recipe_detail.get('sourceUrl', ''),
                        'summary': recipe_detail.get('summary', ''),
                        'instructions': recipe_detail.get('instructions', ''),
                        'cuisines': recipe_detail.get('cuisines', []),
                        'dishTypes': recipe_detail.get('dishTypes', []),
                        'diets': recipe_detail.get('diets', [])
                    }
                    detailed_recipes.append(detailed_recipe)
            except Exception as e:
                print(f"Error fetching recipe details for {recipe['id']}: {e}")
                # Add basic recipe info even if details fail
                detailed_recipes.append({
                    'id': recipe['id'],
                    'title': recipe['title'],
                    # 'image': recipe['image'],
                    'usedIngredientCount': recipe['usedIngredientCount'],
                    'missedIngredientCount': recipe['missedIngredientCount']
                })
        
        # Cache the results
        recipe_cache['data'] = detailed_recipes
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        recipe_cache['backup'] = None  # Clear backup on successful fetch
        print(f"✓ Cached {len(detailed_recipes)} recipes")
        
        return jsonify(detailed_recipes)
        
    except requests.exceptions.Timeout:
        # On timeout, return backup cache if available (from failed refresh)
        if recipe_cache['backup']:
            print("⚠ Timeout - returning backup cached recipes")
            error_result = {'error': 'Request timeout. Showing cached results.', 'recipes': recipe_cache['backup']}
            # Cache this error state
            recipe_cache['data'] = error_result
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            return jsonify(error_result)
        # Otherwise return main cache if available
        if recipe_cache['data']:
            print("⚠ Timeout - returning cached recipes")
            return jsonify({'error': 'Request timeout. Showing cached results.', 'recipes': recipe_cache['data']})
        # No cache available - cache the error
        error_result = {'error': 'Request timeout. Please try again.'}
        recipe_cache['data'] = error_result
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        return jsonify(error_result), 504
    except Exception as e:
        print(f"Error fetching recipes: {e}")
        # On error, return backup cache if available (from failed refresh)
        if recipe_cache['backup']:
            print("⚠ Error - returning backup cached recipes")
            error_result = {'error': str(e), 'recipes': recipe_cache['backup']}
            # Cache this error state
            recipe_cache['data'] = error_result
            recipe_cache['timestamp'] = datetime.now()
            recipe_cache['cache_key'] = cache_key
            return jsonify(error_result)
        # Otherwise return main cache if available
        if recipe_cache['data']:
            print("⚠ Error - returning cached recipes")
            return jsonify({'error': str(e), 'recipes': recipe_cache['data']})
        # No cache available - cache the error
        error_result = {'error': str(e)}
        recipe_cache['data'] = error_result
        recipe_cache['timestamp'] = datetime.now()
        recipe_cache['cache_key'] = cache_key
        return jsonify(error_result), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
