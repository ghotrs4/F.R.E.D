# -------------------------------------------------------------
# 1. IMPORT LIBRARIES
# -------------------------------------------------------------
import torch                       # Main PyTorch library
import torch.nn as nn              # Neural network building blocks
import torch.optim as optim        # Optimizers (Adam, SGD, etc.)
import torchvision                 # Vision datasets + models
import torchvision.transforms as transforms   # Image transforms
from torch.utils.data import DataLoader, Subset, ConcatDataset, Dataset   # For loading subsets
from torchvision.datasets import Food101, ImageFolder          # Food-101 dataset
from torchvision import models                    # Pretrained CNNs
from PIL import Image              # For loading images
import sys
from datetime import datetime
import time


# -------------------------------------------------------------
# LABEL OFFSET WRAPPER (Fix for ConcatDataset label collision)
# -------------------------------------------------------------
class LabelOffsetDataset(Dataset):
    """Wrapper to offset dataset labels by a fixed amount."""
    def __init__(self, dataset, offset):
        self.dataset = dataset
        self.offset = offset
    
    def __len__(self):
        return len(self.dataset)
    
    def __getitem__(self, idx):
        image, label = self.dataset[idx]
        return image, label + self.offset

# Global variables for logging
log_filename = None
log_file = None

def setup_logging():
    """Initialize logging"""
    global log_filename, log_file
    log_filename = f"training_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_file = open(log_filename, 'w', buffering=1)

def log_print(message):
    """Print to both console and log file"""
    print(message)
    if log_file:
        log_file.write(message + '\n')
        log_file.flush()


# -------------------------------------------------------------
# 2. DEFINE IMAGE TRANSFORMS
# -------------------------------------------------------------
# Food-101 images are all different sizes, so we resize them.
# ResNet expects 224×224 images, so we resize to that.
# Using ImageNet normalization (ResNet was pretrained on ImageNet)
transform = transforms.Compose([
    transforms.Resize((224, 224)),   # Make all images 224×224
    transforms.ToTensor(),           # Convert to PyTorch tensors
    transforms.Normalize(            # ImageNet mean and std for better training
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
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
# 4. COMBINE FOOD-101 WITH CUSTOM IMAGES
# -------------------------------------------------------------
def create_combined_dataset():
    """Combine Food-101 with custom images from ./data/custom_foods"""
    import os
    
    custom_dataset = None
    custom_count = 0
    
    # Check if custom_foods directory exists and has subdirectories with images
    custom_foods_path = "./data/custom_foods"
    valid_extensions = {'.jpg', '.jpeg', '.png', '.ppm', '.bmp', '.pgm', '.tif', '.tiff', '.webp'}
    
    if os.path.exists(custom_foods_path):
        # Check if there are any subdirectories with actual image files
        has_images = False
        for subdir in os.listdir(custom_foods_path):
            subdir_path = os.path.join(custom_foods_path, subdir)
            if os.path.isdir(subdir_path):
                # Check if this subdirectory contains any image files
                files = os.listdir(subdir_path)
                if any(os.path.splitext(f)[1].lower() in valid_extensions for f in files):
                    has_images = True
                    break
        
        if has_images:
            # Load custom images (organized in folders by category)
            # Structure: ./data/custom_foods/category_name/image.jpg
            try:
                custom_dataset = ImageFolder(
                    root=custom_foods_path,
                    transform=transform
                )
                custom_count = len(custom_dataset)
            except (FileNotFoundError, RuntimeError) as e:
                print(f"Warning: Could not load custom images: {e}")
                custom_dataset = None
                custom_count = 0
    
    # Combine datasets or use Food-101 only
    if custom_dataset and custom_count > 0:
        # Offset custom dataset labels to avoid collision with Food-101 (0-100)
        offset_custom_dataset = LabelOffsetDataset(custom_dataset, len(train_data_full.classes))
        combined_dataset = ConcatDataset([train_data_full, offset_custom_dataset])
        num_classes = len(train_data_full.classes) + len(custom_dataset.classes)
        all_classes = train_data_full.classes + custom_dataset.classes
    else:
        combined_dataset = train_data_full
        num_classes = len(train_data_full.classes)
        all_classes = train_data_full.classes
    
    return combined_dataset, num_classes, all_classes, custom_count


def create_data_loader(train_data, batch_size, num_workers):
    """Create DataLoader with proper settings"""
    return DataLoader(
        train_data, 
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True if num_workers > 0 else False,
        persistent_workers=True if num_workers > 0 else False
    )


def train_model():
    """Main training function - wrapped for Windows multiprocessing"""
    
    setup_logging()
    
    # COMBINED DATASET VERSION (Food-101 + custom images)
    train_data, num_classes, class_names, custom_count = create_combined_dataset()
    
    # Use multiple workers for faster data loading
    BATCH_SIZE = 256  # Larger batches = better GPU utilization
    NUM_WORKERS = 6   # More parallel workers
    train_loader = create_data_loader(train_data, BATCH_SIZE, NUM_WORKERS)
    
    # -------------------------------------------------------------
    # 5. LOAD A PRETRAINED RESNET18 MODEL
    # -------------------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model = model.to(device)
    
    # -------------------------------------------------------------
    # 6. LOSS FUNCTION + OPTIMIZER + MIXED PRECISION
    # -------------------------------------------------------------
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    
    scaler = torch.amp.GradScaler('cuda') if torch.cuda.is_available() else None
    use_amp = torch.cuda.is_available()
    
    # -------------------------------------------------------------
    # 7. TRAINING LOOP
    # -------------------------------------------------------------
    epochs = 20  # More epochs for better accuracy
    total_batches = len(train_loader)
    
    log_print(f"\nLogging to: {log_filename}")
    log_print(f"Training started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"\nStarting training...")
    log_print(f"Device: {device}")
    log_print(f"Total batches per epoch: {total_batches}")
    log_print(f"Images per epoch: {len(train_data)}")
    log_print(f"  - Food-101 images: {len(train_data_full)}")
    log_print(f"  - Custom images: {custom_count}")
    log_print(f"Number of classes: {num_classes}")
    log_print(f"  - Food-101 classes: {len(train_data_full.classes)}")
    log_print(f"  - Custom classes: {num_classes - len(train_data_full.classes)}")
    log_print(f"Batch size: {BATCH_SIZE}")
    log_print(f"Num workers: {NUM_WORKERS}")
    log_print(f"Number of epochs: {epochs}")
    log_print("="*60)

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        epoch_start_time = time.time()
        
        log_print(f"\n[Epoch {epoch+1}/{epochs}] Starting...")

        for batch_idx, (images, labels) in enumerate(train_loader):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            optimizer.zero_grad()
            
            if use_amp:
                with torch.amp.autocast('cuda'):
                    outputs = model(images)
                    loss = criterion(outputs, labels)
                
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                outputs = model(images)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

            running_loss += loss.item()
            
            if (batch_idx + 1) % 50 == 0:
                current_loss = running_loss / (batch_idx + 1)
                images_processed = (batch_idx + 1) * BATCH_SIZE
                percent = 100 * (batch_idx + 1) / total_batches
                log_print(f"  Batch {batch_idx+1}/{total_batches} ({percent:.1f}%) | "
                          f"Images: {images_processed}/{len(train_data)} | "
                          f"Loss: {current_loss:.4f}")

        epoch_time = time.time() - epoch_start_time
        average_loss = running_loss / len(train_loader)
        log_print(f"[Epoch {epoch+1}/{epochs}] COMPLETED - Loss: {average_loss:.4f} | Time: {epoch_time:.1f}s")
        log_print("="*60)

    # -------------------------------------------------------------
    # 8. TEST ACCURACY
    # -------------------------------------------------------------
    model.eval()
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in train_loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            _, predicted = torch.max(outputs, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

    accuracy = 100 * correct / total
    log_print(f"\nTraining accuracy on {len(train_data)} images: {accuracy:.2f}%")

    # -------------------------------------------------------------
    # 9. SAVE THE MODEL
    # -------------------------------------------------------------
    model_filename = f"food_classifier_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pth"
    torch.save({
        'model_state_dict': model.state_dict(),
        'num_classes': num_classes,
        'class_names': class_names
    }, model_filename)
    log_print(f"\nModel saved as '{model_filename}'")
    log_print(f"Saved with {num_classes} classes")
    log_print(f"Training completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if log_file:
        log_file.close()
    print(f"\nLog saved to: {log_filename}")
    
    return model


# Windows multiprocessing protection
if __name__ == '__main__':
    train_model()
