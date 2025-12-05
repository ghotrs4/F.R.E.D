# -------------------------------------------------------------
# 1. IMPORT LIBRARIES
# -------------------------------------------------------------
import torch                       # Main PyTorch library
import torch.nn as nn              # Neural network building blocks
import torch.optim as optim        # Optimizers (Adam, SGD, etc.)
import torchvision                 # Vision datasets + models
import torchvision.transforms as transforms   # Image transforms
from torch.utils.data import DataLoader, Subset   # For loading subsets
from torchvision.datasets import Food101          # Food-101 dataset
from torchvision import models                    # Pretrained CNNs
from PIL import Image              # For loading images


# -------------------------------------------------------------
# 2. DEFINE IMAGE TRANSFORMS
# -------------------------------------------------------------
# Food-101 images are all different sizes, so we resize them.
# ResNet expects 224×224 images, so we resize to that.
transform = transforms.Compose([
    transforms.Resize((224, 224)),   # Make all images 224×224
    transforms.ToTensor(),           # Convert to PyTorch tensors
])


# -------------------------------------------------------------
# 3. LOAD FOOD-101 DATASET
# -------------------------------------------------------------
# This will automatically download the dataset (about 5GB).
# "split='train'" loads the training portion.
train_data_full = Food101(
    root="./data",
    split="train",
    transform=transform,
    download=True
)

# "split='test'" loads the test portion.
test_data_full = Food101(
    root="./data",
    split="test",
    transform=transform,
    download=True
)


# -------------------------------------------------------------
# 4. CREATE A SMALL SUBSET (1000 IMAGES) FOR FAST TESTING
# -------------------------------------------------------------
# Food-101 has 75,750 training images — too slow for testing.
# So we take only the first range_num images to verify our code works.
range_num = 1000
train_subset_indices = list(range(range_num))    # Use only range_num images
train_data = Subset(train_data_full, train_subset_indices)

# DataLoader lets the model load images in batches.
train_loader = DataLoader(train_data, batch_size=5, shuffle=True)


# -------------------------------------------------------------
# 5. LOAD A PRETRAINED RESNET18 MODEL
# -------------------------------------------------------------
# If your system has a GPU, use it. Otherwise use CPU.
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Load pretrained ResNet18 weights (trained on ImageNet)
model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)

# ResNet outputs 1000 classes by default.
# Food-101 has 101 classes → so we replace the final layer.
model.fc = nn.Linear(model.fc.in_features, 101)

# Move the model onto your GPU/CPU
model = model.to(device)


# -------------------------------------------------------------
# 6. LOSS FUNCTION + OPTIMIZER
# -------------------------------------------------------------
criterion = nn.CrossEntropyLoss()           # Good for classification
optimizer = optim.Adam(model.parameters(), lr=0.001)  # Learning rate


# -------------------------------------------------------------
# 7. TRAINING LOOP
# -------------------------------------------------------------
epochs = 10   # Just 10 epochs for testing

for epoch in range(epochs):
    model.train()             # Set model to training mode
    running_loss = 0.0        # Track loss over batches

    for images, labels in train_loader:
        images = images.to(device)         # Move images to GPU/CPU
        labels = labels.to(device)         # Move labels to GPU/CPU

        optimizer.zero_grad()              # Reset previous gradients
        outputs = model(images)            # Forward pass
        loss = criterion(outputs, labels)  # Compute loss
        loss.backward()                    # Backpropagation
        optimizer.step()                   # Update weights

        running_loss += loss.item()        # Add to total loss

    average_loss = running_loss / len(train_loader)
    print(f"Epoch {epoch+1}/{epochs} - Loss: {average_loss:.4f}")


# -------------------------------------------------------------
# 8. TEST ACCURACY ON THE TRAINING SUBSET
# -------------------------------------------------------------
model.eval()       # Switch to evaluation mode
correct = 0        # Count correctly predicted images
total = 0          # Count total images

with torch.no_grad():  # No gradient needed for testing
    for images, labels in train_loader:
        images = images.to(device)
        labels = labels.to(device)

        outputs = model(images)              # Forward pass
        _, predicted = torch.max(outputs, 1) # Choose top class

        total += labels.size(0)
        correct += (predicted == labels).sum().item()

accuracy = 100 * correct / total
print(f"\nAccuracy on {range_num} Food-101 images: {accuracy:.2f}%")


# -------------------------------------------------------------
# 9. SAVE THE MODEL
# -------------------------------------------------------------
torch.save(model.state_dict(), "food_classifier.pth")
print("\nModel saved as 'food_classifier.pth'")


# -------------------------------------------------------------
# 10. FUNCTION TO CLASSIFY A SINGLE IMAGE
# -------------------------------------------------------------

# Classify a food image from a file path
def predict_food(image_path):
  
    # Get class names from the dataset
    class_names = train_data_full.classes
    
    # Load and preprocess the image
    img = Image.open(image_path).convert('RGB')
    img_tensor = transform(img).unsqueeze(0)  # Add batch dimension
    img_tensor = img_tensor.to(device)
    
    # Make prediction
    model.eval()
    with torch.no_grad():
        output = model(img_tensor)
        probabilities = torch.nn.functional.softmax(output[0], dim=0)
        confidence, predicted_idx = torch.max(probabilities, 0)
    
    predicted_class = class_names[predicted_idx.item()]
    confidence_percent = confidence.item() * 100
    
    return predicted_class, confidence_percent


# -------------------------------------------------------------
# 11. EXAMPLE USAGE - CLASSIFY A NEW IMAGE
# -------------------------------------------------------------
# Uncomment the lines below to test with your own image:
#
result_class, result_confidence = predict_food("data/image.jpg")
print(f"\nPrediction: {result_class}")
print(f"Confidence: {result_confidence:.2f}%")
