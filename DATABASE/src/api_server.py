from flask import Flask, jsonify, request
from flask_cors import CORS
import csv
import os
from datetime import datetime, timedelta
from spoilage_algorithm import predict_spoilage
from sensor_interface import get_sensor

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend connection

# Path to the CSV database
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'database.csv')

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
