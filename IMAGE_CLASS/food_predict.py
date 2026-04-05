# -------------------------------------------------------------
# FOOD-101 PREDICTION SCRIPT
# Load trained model and make predictions on test data
# -------------------------------------------------------------

import torch
import torch.nn as nn
import torchvision.transforms as transforms
from torchvision.datasets import Food101
from torchvision import models
from torch.utils.data import DataLoader
from PIL import Image
import os

# -------------------------------------------------------------
# 1. SETUP & CONFIGURATION
# -------------------------------------------------------------
# CHOOSE YOUR TEST MODE:
# Set to True to test a single image, False to test on full 25,250 image dataset
TEST_SINGLE_IMAGE = True  # Testing on full dataset to see real accuracy

# If testing single image, specify the path here:
#SINGLE_IMAGE_PATH = "./data/food-101/images/apple_pie/1005649.jpg"  # Change to your image path
#SINGLE_IMAGE_PATH = "./data/churro.jpg"
#SINGLE_IMAGE_PATH = "./data/Homemade-Sandwich-Bread-0008.jpg"  # Example image (bread)

SINGLE_IMAGE_PATH = "./data/milk-bread.webp"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
print(f"Test mode: {'Single Image' if TEST_SINGLE_IMAGE else 'Full Dataset (25,250 images)'}")

# Image transforms (MUST match training exactly!)
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(  # Same normalization as training
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

# -------------------------------------------------------------
# 2. LOAD THE TRAINED MODEL
# -------------------------------------------------------------
print("\nLoading trained model...")

# Load the trained weights
#model_path = "50EPOCH.pth"

model_path = "food_classifier_20260404_211058.pth" #name of custom trained model

if not os.path.exists(model_path):
    print(f"✗ Error: Model file '{model_path}' not found!")
    exit(1)

# Load checkpoint
checkpoint = torch.load(model_path, map_location=device)

# Extract metadata and model state
if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
    # New format with metadata
    num_classes = checkpoint.get('num_classes', 101)
    saved_class_names = checkpoint.get('class_names', None)
    model_state = checkpoint['model_state_dict']
    print(f"✓ Model checkpoint loaded with {num_classes} classes")
else:
    # Old format (just state dict)
    num_classes = 101
    saved_class_names = None
    model_state = checkpoint
    print(f"✓ Model loaded (old format, assuming 101 classes)")

# Create model architecture with correct number of classes
model = models.resnet18(weights=None)  # Don't load pretrained weights
model.fc = nn.Linear(model.fc.in_features, num_classes)
model = model.to(device)

# Load the weights
model.load_state_dict(model_state)
print(f"✓ Model weights loaded successfully")

model.eval()  # Set to evaluation mode

# -------------------------------------------------------------
# 3. LOAD TEST DATASET (for class names)
# -------------------------------------------------------------
if saved_class_names:
    # Use class names from saved model (includes custom classes)
    class_names = saved_class_names
    print(f"\n✓ Using {len(class_names)} class names from saved model")
    print(f"  - Includes Food-101 and custom classes")
else:
    # Fallback to Food-101 only
    print("\nLoading Food-101 dataset for class names...")
    test_data = Food101(
        root="./data",
        split="test",
        transform=transform,
        download=False  # Assuming already downloaded
    )

    # Get class names
    class_names = test_data.classes
    print(f"✓ Dataset has {len(class_names)} classes")

# -------------------------------------------------------------
# 4. RUN PREDICTIONS BASED ON MODE
# -------------------------------------------------------------

if TEST_SINGLE_IMAGE:
    # ========== SINGLE IMAGE MODE ==========
    print(f"\n{'='*60}")
    print("SINGLE IMAGE PREDICTION MODE")
    print(f"{'='*60}")
    print(f"Image path: {SINGLE_IMAGE_PATH}")
    
    if not os.path.exists(SINGLE_IMAGE_PATH):
        print(f"✗ Error: Image file '{SINGLE_IMAGE_PATH}' not found!")
        print("Please update SINGLE_IMAGE_PATH at the top of the script.")
        exit(1)
    
    # Load and transform the image
    image = Image.open(SINGLE_IMAGE_PATH).convert('RGB')
    image_tensor = transform(image).unsqueeze(0).to(device)
    
    # Make prediction
    with torch.no_grad():
        output = model(image_tensor)
        probabilities = torch.softmax(output, 1)[0]
        
        # Top prediction
        confidence, predicted_idx = torch.max(probabilities, 0)
        predicted_class = class_names[predicted_idx.item()]
        
        # Top 5 predictions
        top5_prob, top5_idx = torch.topk(probabilities, 5)
        top5_predictions = [
            (class_names[idx.item()], prob.item() * 100)
            for idx, prob in zip(top5_idx, top5_prob)
        ]
    
    # Display results
    print(f"\nPredicted class: {predicted_class}")
    print(f"Confidence: {confidence.item() * 100:.2f}%")
    print(f"\nTop 5 predictions:")
    for i, (cls, prob) in enumerate(top5_predictions, 1):
        print(f"  {i}. {cls:25s} {prob:.2f}%")
    print(f"{'='*60}\n")

else:
    # ========== FULL DATASET MODE ==========
    print(f"\n{'='*60}")
    print("FULL DATASET PREDICTION MODE")
    print(f"{'='*60}")
    print(f"Testing on {len(test_data)} images...")
    
    # Use a reasonable batch size
    test_loader = DataLoader(test_data, batch_size=32, shuffle=False)

    correct = 0
    total = 0
    top5_correct = 0

    # Store some predictions for display
    sample_predictions = []

    with torch.no_grad():
        for batch_idx, (images, labels) in enumerate(test_loader):
            images = images.to(device)
            labels = labels.to(device)
            
            # Forward pass
            outputs = model(images)
            
            # Top-1 prediction
            _, predicted = torch.max(outputs, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            
            # Top-5 accuracy
            _, top5_pred = outputs.topk(5, 1, largest=True, sorted=True)
            top5_correct += sum([labels[i].item() in top5_pred[i].tolist() for i in range(len(labels))])
            
            # Save first 10 predictions as examples
            if len(sample_predictions) < 10:
                for i in range(min(5, len(labels))):
                    if len(sample_predictions) >= 10:
                        break
                    
                    true_label = class_names[labels[i].item()]
                    pred_label = class_names[predicted[i].item()]
                    confidence = torch.softmax(outputs[i], 0)[predicted[i]].item() * 100
                    
                    sample_predictions.append({
                        'true': true_label,
                        'predicted': pred_label,
                        'confidence': confidence,
                        'correct': predicted[i].item() == labels[i].item()
                    })
            
            # Progress indicator
            if (batch_idx + 1) % 100 == 0:
                current_acc = 100 * correct / total
                print(f"  Processed {total}/{len(test_data)} images | Accuracy so far: {current_acc:.2f}%")

    # -------------------------------------------------------------
    # 5. DISPLAY FULL DATASET RESULTS
    # -------------------------------------------------------------
    accuracy = 100 * correct / total
    top5_accuracy = 100 * top5_correct / total

    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    print(f"Total test images: {total}")
    print(f"Top-1 Accuracy: {accuracy:.2f}%")
    print(f"Top-5 Accuracy: {top5_accuracy:.2f}%")
    print(f"Correctly classified: {correct}/{total}")
    print(f"Incorrectly classified: {total - correct}/{total}")

    print("\n" + "="*60)
    print("SAMPLE PREDICTIONS")
    print("="*60)
    for idx, pred in enumerate(sample_predictions, 1):
        status = "✓" if pred['correct'] else "✗"
        print(f"{idx}. {status} True: {pred['true']:20s} | Predicted: {pred['predicted']:20s} | Confidence: {pred['confidence']:.1f}%")

    print("\n" + "="*60)

# -------------------------------------------------------------
# 6. OPTIONAL: PREDICT ON A SINGLE IMAGE
# -------------------------------------------------------------
def predict_single_image(image_path):
    """
    Predict the class of a single image file.
    
    Args:
        image_path: Path to the image file
    
    Returns:
        predicted_class, confidence, top5_predictions
    """
    if not os.path.exists(image_path):
        print(f"Error: Image file '{image_path}' not found!")
        return None
    
    # Load and transform the image
    image = Image.open(image_path).convert('RGB')
    image_tensor = transform(image).unsqueeze(0).to(device)
    
    # Make prediction
    with torch.no_grad():
        output = model(image_tensor)
        probabilities = torch.softmax(output, 1)[0]
        
        # Top prediction
        confidence, predicted_idx = torch.max(probabilities, 0)
        predicted_class = class_names[predicted_idx.item()]
        
        # Top 5 predictions
        top5_prob, top5_idx = torch.topk(probabilities, 5)
        top5_predictions = [
            (class_names[idx.item()], prob.item() * 100)
            for idx, prob in zip(top5_idx, top5_prob)
        ]
    
    return predicted_class, confidence.item() * 100, top5_predictions


# Example usage (uncomment to use):
# print("\n" + "="*60)
# print("SINGLE IMAGE PREDICTION EXAMPLE")
# print("="*60)
# image_path = "./data/food-101/images/apple_pie/1005649.jpg"  # Replace with your image
# if os.path.exists(image_path):
#     pred_class, conf, top5 = predict_single_image(image_path)
#     print(f"\nImage: {image_path}")
#     print(f"Predicted: {pred_class} ({conf:.2f}% confidence)")
#     print("\nTop 5 predictions:")
#     for i, (cls, prob) in enumerate(top5, 1):
#         print(f"  {i}. {cls:25s} {prob:.2f}%")
