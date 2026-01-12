"""
F.R.E.D. Database System
Manages food items in refrigerator with CSV backend
"""

import csv
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List
from sensor_interface import get_sensor


@dataclass
class FoodItem:
    """
    Data structure for each food item in the fridge.
    All fields required by spoilage prediction algorithm.
    """
    # Unique identifier
    item_id: str
    
    # Food information
    food_name: str                    # User-friendly name (e.g., "Organic Milk")
    food_category: str                # Category for algorithm (e.g., 'dairy_milk')
    
    # Timestamps
    purchase_date: str                # ISO format: "2025-12-05T10:30:00"
    entry_date: str                   # When added to system
    expiration_date: Optional[str] = None  # Listed expiry date (ISO format)
    
    # Environmental data at entry
    temp_at_entry: float = 4.0        # Temperature when added (°C)
    humidity_at_entry: float = 50.0   # Humidity when added (%)
    
    # Storage information
    packaging_type: str = 'sealed'    # 'vacuum', 'sealed', 'opened', 'loose'
    location: str = 'main'            # Shelf location (optional)
    quantity: str = '1'               # Amount/quantity (optional)
    
    # Tracking data
    cumulative_temp_abuse: float = 0.0  # Hours above safe temperature
    last_check_date: str = None       # Last time freshness was calculated
    
    # Calculated fields (updated by algorithm)
    freshness_score: float = 100.0    # 0-100
    days_until_spoilage: float = 0.0  # Estimated days remaining
    safety_category: str = 'Fresh'    # 'Fresh', 'Good', 'Caution', 'Spoiled'
    
    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        """Create FoodItem from dictionary"""
        return cls(**data)


class Database:
    """
    Database class for managing food items.
    Backend: CSV file storage
    """
    
    CSV_HEADERS = [
        'item_id', 'food_name', 'food_category', 
        'purchase_date', 'entry_date', 'expiration_date',
        'temp_at_entry', 'humidity_at_entry',
        'packaging_type', 'location', 'quantity',
        'cumulative_temp_abuse', 'last_check_date',
        'freshness_score', 'days_until_spoilage', 'safety_category'
    ]
    
    def __init__(self, csv_path: str = '../data/database.csv'):
        """Initialize database with CSV file path"""
        self.csv_path = csv_path
        self.items = []
        self.sensor = get_sensor()  # Access to current sensor readings
        
        # Create CSV file with headers if it doesn't exist
        if not os.path.exists(self.csv_path):
            self._create_csv()
        else:
            self.load_from_csv()
    
    def _create_csv(self):
        """Create new CSV file with headers"""
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        with open(self.csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
            writer.writeheader()
    
    def load_from_csv(self):
        """Load all items from CSV file"""
        self.items = []
        try:
            with open(self.csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert numeric fields
                    row['temp_at_entry'] = float(row.get('temp_at_entry', 4.0))
                    row['humidity_at_entry'] = float(row.get('humidity_at_entry', 50.0))
                    row['cumulative_temp_abuse'] = float(row.get('cumulative_temp_abuse', 0.0))
                    row['freshness_score'] = float(row.get('freshness_score', 100.0))
                    row['days_until_spoilage'] = float(row.get('days_until_spoilage', 0.0))
                    
                    item = FoodItem.from_dict(row)
                    self.items.append(item)
        except FileNotFoundError:
            self._create_csv()
    
    def save_to_csv(self):
        """Save all items to CSV file"""
        with open(self.csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
            writer.writeheader()
            for item in self.items:
                writer.writerow(item.to_dict())
    
    def add_item(self, item: FoodItem, use_current_sensor: bool = True) -> bool:
        """
        Add new food item to database.
        
        Args:
            item: FoodItem object
            use_current_sensor: If True, automatically set temp/humidity from sensor
            
        Returns:
            True if successful, False if item_id already exists
        """
        # Check if ID already exists
        if any(existing.item_id == item.item_id for existing in self.items):
            return False
        
        # Automatically populate temp/humidity from current sensor readings
        if use_current_sensor:
            item.temp_at_entry = self.sensor.get_temperature()
            item.humidity_at_entry = self.sensor.get_humidity()
        
        self.items.append(item)
        self.save_to_csv()
        return True
    
    def create_and_add_item(self, food_name: str, food_category: str, 
                           purchase_date: str, packaging_type: str = 'sealed',
                           expiration_date: Optional[str] = None,
                           location: str = 'main', quantity: str = '1') -> Optional[FoodItem]:
        """
        Convenience method to create and add item with current sensor readings.
        
        Args:
            food_name: User-friendly name
            food_category: Category for algorithm (e.g., 'dairy_milk')
            purchase_date: ISO format datetime string
            packaging_type: 'sealed', 'opened', 'vacuum', 'loose'
            expiration_date: Optional expiration date (ISO format)
            location: Shelf location
            quantity: Amount
            
        Returns:
            Created FoodItem if successful, None if failed
        """
        # Create new item with auto-generated ID and current sensor readings
        item = FoodItem(
            item_id=self.generate_id(),
            food_name=food_name,
            food_category=food_category,
            purchase_date=purchase_date,
            entry_date=datetime.now().isoformat(),
            expiration_date=expiration_date,
            temp_at_entry=self.sensor.get_temperature(),  # Automatically from sensor
            humidity_at_entry=self.sensor.get_humidity(),  # Automatically from sensor
            packaging_type=packaging_type,
            location=location,
            quantity=quantity
        )
        
        if self.add_item(item, use_current_sensor=False):  # Already set values above
            return item
        return None
    
    def remove_item(self, item_id: str) -> bool:
        """
        Remove item from database by ID.
        
        Args:
            item_id: Unique identifier
            
        Returns:
            True if removed, False if not found
        """
        original_length = len(self.items)
        self.items = [item for item in self.items if item.item_id != item_id]
        
        if len(self.items) < original_length:
            self.save_to_csv()
            return True
        return False
    
    def get_item(self, item_id: str) -> Optional[FoodItem]:
        """
        Get item by ID.
        
        Args:
            item_id: Unique identifier
            
        Returns:
            FoodItem object or None if not found
        """
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None
    
    def update_item(self, item_id: str, **kwargs) -> bool:
        """
        Update item fields.
        
        Args:
            item_id: Unique identifier
            **kwargs: Fields to update
            
        Returns:
            True if updated, False if not found
        """
        item = self.get_item(item_id)
        if not item:
            return False
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        
        self.save_to_csv()
        return True
    
    def get_all_items(self) -> List[FoodItem]:
        """Return all items in database"""
        return self.items
    
    def get_items_by_category(self, category: str) -> List[FoodItem]:
        """Get all items of a specific food category"""
        return [item for item in self.items if item.food_category == category]
    
    def get_items_by_safety(self, safety_category: str) -> List[FoodItem]:
        """Get items by safety category (Fresh, Good, Caution, Spoiled)"""
        return [item for item in self.items if item.safety_category == safety_category]
    
    def get_expiring_soon(self, days_threshold: float = 2.0) -> List[FoodItem]:
        """Get items expiring within threshold days"""
        return [item for item in self.items if item.days_until_spoilage <= days_threshold]
    
    def generate_id(self) -> str:
        """Generate unique ID for new item"""
        if not self.items:
            return "ITEM_001"
        
        # Extract numeric part from last item ID
        try:
            last_id = self.items[-1].item_id
            num = int(last_id.split('_')[1])
            return f"ITEM_{num+1:03d}"
        except:
            return f"ITEM_{len(self.items)+1:03d}"


# Example usage
if __name__ == "__main__":
    # Simulate sensor reading
    sensor = get_sensor()
    sensor_output = """
    Temperature = 4.5 °C
    Pressure = 1001.48 hPa
    Approx. Altitude = 98.48 m
    Humidity = 55.0 %
    """
    sensor.parse_sensor_output(sensor_output)
    print("✓ Sensor readings updated")
    print(f"Current temp: {sensor.get_temperature()}°C")
    print(f"Current humidity: {sensor.get_humidity()}%\n")
    
    # Create database
    db = Database()
    
    # Method 1: Use convenience method (recommended)
    milk = db.create_and_add_item(
        food_name="Organic 2% Milk",
        food_category="dairy_milk",
        purchase_date=datetime.now().isoformat(),
        packaging_type="opened",
        location="door_shelf",
        quantity="1 gallon"
    )
    
    if milk:
        print(f"✓ Added: {milk.food_name}")
        print(f"  - ID: {milk.item_id}")
        print(f"  - Temp at entry: {milk.temp_at_entry}°C (from sensor)")
        print(f"  - Humidity at entry: {milk.humidity_at_entry}% (from sensor)")
    
    # Method 2: Manual creation (if you need more control)
    eggs = FoodItem(
        item_id=db.generate_id(),
        food_name="Organic Eggs",
        food_category="eggs",
        purchase_date=datetime.now().isoformat(),
        entry_date=datetime.now().isoformat(),
        packaging_type="sealed",
        location="middle_shelf",
        quantity="1 dozen"
    )
    
    # Add with automatic sensor reading
    if db.add_item(eggs, use_current_sensor=True):
        print(f"\n✓ Added: {eggs.food_name}")
        print(f"  - Temp at entry: {eggs.temp_at_entry}°C (auto-populated)")
    
    # Display all items
    print(f"\n{'='*50}")
    print(f"Total items in fridge: {len(db.get_all_items())}")
    for item in db.get_all_items():
        print(f"  - {item.food_name} ({item.food_category})")
        print(f"    Stored at: {item.temp_at_entry}°C, {item.humidity_at_entry}%")
