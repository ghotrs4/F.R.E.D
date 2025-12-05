# F.R.E.D. Spoilage Prediction Algorithm

Simple rule-based spoilage prediction using food science principles.

## Quick Start

```python
from datetime import datetime, timedelta
from spoilage_algorithm import predict_spoilage

# Predict spoilage for milk opened 3 days ago
result = predict_spoilage(
    food_category='dairy_milk',
    purchase_date=datetime.now() - timedelta(days=3),
    current_temp=5.0,
    packaging_type='opened',
    cumulative_temp_abuse=2.0
)

print(f"Freshness: {result['freshness_score']}/100")
print(f"Days left: {result['days_until_spoilage']}")
print(f"Status: {result['safety_category']}")
```

## Usage

Run example:
```bash
python spoilage_algorithm.py
```

## Supported Food Categories

- `dairy_milk`, `dairy_cheese_hard`, `dairy_yogurt`
- `meat_chicken_raw`, `meat_beef_raw`, `meat_ground`
- `produce_lettuce`, `produce_berries`
- `eggs`
- `leftovers`

## Outputs

- **freshness_score**: 0-100 (100 = perfectly fresh)
- **days_until_spoilage**: Estimated days remaining
- **safety_category**: Fresh, Good, Caution, or Spoiled
- **warnings**: List of safety warnings
