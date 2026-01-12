"""
F.R.E.D. Spoilage Prediction Algorithm
Core algorithm for predicting food freshness and spoilage timing
"""

from datetime import datetime
import math


# Food database with spoilage parameters based on USDA guidelines
FOOD_DATABASE = {
    # DAIRY
    'dairy': {
        'name': 'Dairy',
        'shelf_life_days': 14,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.8,
        'temp_abuse_threshold': 12.0,
    },
    
    # MEAT
    'meat': {
        'name': 'Meat',
        'shelf_life_days': 3,
        'optimal_temp': 2.0,
        'temp_sensitivity': 2.8,
        'temp_abuse_threshold': 3.0,
    },
    
    # PRODUCE
    'produce': {
        'name': 'Produce',
        'shelf_life_days': 7,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.5,
        'temp_abuse_threshold': 12.0,
    },
    
    # BEVERAGE
    'beverage': {
        'name': 'Beverage',
        'shelf_life_days': 10,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.3,
        'temp_abuse_threshold': 24.0,
    },
    
    # CONDIMENT
    'condiment': {
        'name': 'Condiment',
        'shelf_life_days': 90,
        'optimal_temp': 4.0,
        'temp_sensitivity': 0.8,
        'temp_abuse_threshold': 72.0,
    },
    
    # PREPARED/LEFTOVERS
    'prepared': {
        'name': 'Prepared',
        'shelf_life_days': 4,
        'optimal_temp': 4.0,
        'temp_sensitivity': 2.5,
        'temp_abuse_threshold': 4.0,
    },
    
    # DEFAULT
    'other': {
        'name': 'Other',
        'shelf_life_days': 7,
        'optimal_temp': 4.0,
        'temp_sensitivity': 1.5,
        'temp_abuse_threshold': 12.0,
    },
}


def calculate_temperature_factor(current_temp, optimal_temp, sensitivity):
    """
    Calculate spoilage rate based on temperature using Arrhenius equation.
    Returns a factor that multiplies shelf life (< 1 = faster spoilage)
    """
    delta_T = current_temp - optimal_temp
    
    if delta_T <= 0:
        # At or below optimal - slight benefit
        return min(1.2, 1.0 + abs(delta_T) * 0.02)
    else:
        # Above optimal - accelerated spoilage
        T_current = current_temp + 273.15
        T_optimal = optimal_temp + 273.15
        Ea_R = 3000 * sensitivity
        arrhenius = math.exp(-Ea_R * (1/T_current - 1/T_optimal))
        return max(0.1, 1.0 / arrhenius)


def calculate_temp_abuse_factor(cumulative_hours, threshold_hours):
    """Calculate degradation from cumulative temperature abuse"""
    if cumulative_hours <= 0:
        return 1.0
    
    if cumulative_hours <= threshold_hours:
        # Minor abuse
        return 1.0 - (0.1 * cumulative_hours / threshold_hours)
    else:
        # Significant abuse - exponential impact
        excess = cumulative_hours - threshold_hours
        return max(0.2, 0.9 * math.exp(-excess / threshold_hours))


def calculate_packaging_factor(packaging_type):
    """Get packaging protection factor"""
    factors = {
        'vacuum': 1.2,
        'sealed': 1.0,
        'opened': 0.7,
        'loose': 0.5,
        'carton': 1.0,
        'bottle': 1.1,
        'jar': 1.0,
    }
    return factors.get(packaging_type.lower() if packaging_type else 'sealed', 1.0)


def calculate_freshness_score(days_since_purchase, effective_shelf_life):
    """Calculate freshness score 0-100 based on shelf life consumed"""
    if effective_shelf_life <= 0:
        return 0.0
    
    life_fraction = days_since_purchase / effective_shelf_life
    score = 100 * (1 - life_fraction)
    return max(0.0, min(100.0, score))


def categorize_safety(freshness_score, days_remaining):
    """Determine safety category"""
    if freshness_score >= 75 and days_remaining > 3:
        return 'Fresh'
    elif freshness_score >= 50 and days_remaining > 1:
        return 'Good'
    elif freshness_score >= 25:
        return 'Caution'
    else:
        return 'Spoiled'


def predict_spoilage(
    food_category,
    purchase_date,
    current_temp=4.0,
    current_humidity=50.0,
    packaging_type='sealed',
    cumulative_temp_abuse=0.0,
    expiration_date=None
):
    """
    Main spoilage prediction function.
    
    Args:
        food_category: Category from FOOD_DATABASE (lowercase)
        purchase_date: datetime when purchased
        current_temp: Current temperature in Celsius
        current_humidity: Current relative humidity %
        packaging_type: 'vacuum', 'sealed', 'opened', or 'loose'
        cumulative_temp_abuse: Total hours above safe temperature
        expiration_date: Optional expiration date
    
    Returns:
        dict with:
            - freshness_score: 0-100
            - days_until_spoilage: float
            - safety_category: 'Fresh', 'Good', 'Caution', or 'Spoiled'
            - warnings: list of warning messages
    """
    
    # Normalize category to lowercase
    food_category = food_category.lower() if food_category else 'other'
    
    # Get food parameters
    if food_category not in FOOD_DATABASE:
        food_category = 'other'
    
    food = FOOD_DATABASE[food_category]
    
    # Calculate days since purchase
    days_since_purchase = (datetime.now() - purchase_date).total_seconds() / 86400
    
    # Determine baseline shelf life
    if expiration_date:
        baseline_shelf_life = (expiration_date - purchase_date).total_seconds() / 86400
    else:
        baseline_shelf_life = food['shelf_life_days']
    
    # Calculate environmental factors
    temp_factor = calculate_temperature_factor(
        current_temp, 
        food['optimal_temp'],
        food['temp_sensitivity']
    )
    
    abuse_factor = calculate_temp_abuse_factor(
        cumulative_temp_abuse,
        food['temp_abuse_threshold']
    )
    
    packaging_factor = calculate_packaging_factor(packaging_type)
    
    # Calculate effective shelf life
    effective_shelf_life = baseline_shelf_life * temp_factor * abuse_factor * packaging_factor
    
    # Calculate outputs
    freshness_score = calculate_freshness_score(days_since_purchase, effective_shelf_life)
    days_until_spoilage = max(0, effective_shelf_life - days_since_purchase)
    safety_category = categorize_safety(freshness_score, days_until_spoilage)
    
    # Generate warnings
    warnings = []
    if current_temp > food['optimal_temp'] + 3:
        warnings.append(f"Temperature too high ({current_temp}°C)")
    if cumulative_temp_abuse > food['temp_abuse_threshold']:
        warnings.append(f"Significant temperature abuse detected")
    if safety_category == 'Spoiled':
        warnings.append("DISCARD - Food likely spoiled")
    elif safety_category == 'Caution':
        warnings.append("Consume soon")
    
    return {
        'freshness_score': round(freshness_score, 1),
        'days_until_spoilage': round(days_until_spoilage, 1),
        'safety_category': safety_category,
        'warnings': warnings,
        'metadata': {
            'days_since_purchase': round(days_since_purchase, 1),
            'effective_shelf_life': round(effective_shelf_life, 1),
            'temp_factor': round(temp_factor, 3),
            'abuse_factor': round(abuse_factor, 3),
            'packaging_factor': round(packaging_factor, 3)
        }
    }
