# Google Gemini Setup for Food Classification

## Steps to Enable Food Scanning

### 1. Get Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated API key

### 2. Add API Key to Environment
Open `DATABASE/.env` and replace `your_gemini_api_key_here` with your actual API key:
```
GEMINI_API_KEY=AIzaSy...your_actual_key_here
```

### 3. Install Dependencies
```bash
cd DATABASE
pip install -r requirements.txt
```

This will install:
- `google-generativeai` - Gemini API client
- `pillow` - Image processing

### 4. Start the Backend
```bash
cd DATABASE/src
python api_server.py
```

### 5. Start the Frontend
```bash
cd UI
npm run dev
```

### 6. Test the Feature
1. Open the app in your browser
2. Click "📷 Scan New Item" button on the home page
3. Allow camera access when prompted
4. Take a photo of a food item
5. Wait 2-3 seconds for Gemini to classify
6. Review and modify the results
7. Click "Save to Inventory"

## API Usage & Limits

**Free Tier:**
- 15 requests per minute
- 1,500 requests per day
- More than enough for personal use

**Pricing (if you exceed free tier):**
- $0.00025 per image (~4000 images for $1)

## Benefits vs Local Model

✅ **No model file needed** - Saves ~100MB  
✅ **Broader food recognition** - Not limited to 101 categories  
✅ **Better accuracy** - Trained on much more data  
✅ **Understands context** - Can identify packaged foods, brands, etc.  
✅ **Simpler code** - 75% less code than PyTorch version  

## Troubleshooting

**Error: "Gemini API key not configured"**
- Make sure you added the API key to `.env`
- Restart the backend server after adding the key

**Error: "API key not valid"**
- Double-check your API key is correct
- Make sure there are no extra spaces
- Verify the key is enabled in Google AI Studio

**Slow responses**
- First request may take 3-5 seconds
- Subsequent requests are faster (~2 seconds)
- This is normal for cloud AI APIs

**Classification seems wrong**
- Take photos with good lighting
- Center the food item in the frame
- Avoid cluttered backgrounds
- Try again if needed - Gemini provides multiple guesses

## Next Steps

The scanning feature is now ready to use! No additional setup required.

You can test with various foods:
- Fresh produce (apples, carrots, etc.)
- Packaged items
- Prepared meals
- Multiple items in one photo
