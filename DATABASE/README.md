# F.R.E.D Database API

## High Level Overview

-> Utility to keep track of all foods currently in the fridge
-> Python Flask API to add, remove, modify entries
-> Backend is a CSV text file (`data/database.csv`)
-> API is called by frontend UI (Vue.js)

## Setup & Usage

### 1. Install Dependencies
```bash
cd DATABASE
pip install -r requirements.txt
```

### 2. Start the API Server
```bash
cd DATABASE/src
python api_server.py
```

The server runs on `http://localhost:5000`

### 3. Start the Frontend
```bash
cd UI
npm run dev
```

The UI will automatically connect to the API and fetch data every 3 seconds.

## API Endpoints

- **GET** `/api/foods` - Get all food items
- **GET** `/api/foods/:id` - Get specific food item
- **POST** `/api/foods` - Create new food item
- **PUT** `/api/foods/:id` - Update food item
- **DELETE** `/api/foods/:id` - Delete food item

## Data Flow

```
UI (Vue.js) <--> Flask API <--> CSV Database
   Port 5173       Port 5000      data/database.csv
```

## CSV Database Schema

Fields: `item_id`, `food_name`, `food_category`, `entry_date`, `expiration_date`, `temp_at_entry`, `humidity_at_entry`, `packaging_type`, `cumulative_temp_abuse`, `freshness_score`, `days_until_spoilage`, `safety_category`

**Note:** `freshness_score` and `days_until_spoilage` are calculated in real-time using the spoilage algorithm based on:
- Current temperature from sensors
- Time since entry (when food was added to fridge)
- Temperature abuse history
- Packaging type
- Food category parameters
