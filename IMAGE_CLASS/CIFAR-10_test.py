import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, Subset
from torchvision import models

# --- 1. Transformations ---
transform = transforms.Compose([
    transforms.Resize((224, 224)),  # Resize to match ResNet input
    transforms.ToTensor(),
])

# --- 2. Load CIFAR-10 full dataset ---
train_data_full = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)

# --- 3. Take only the first 10 images ---
train_indices = list(range(10))  # all 10 images
train_data = Subset(train_data_full, train_indices)
train_loader = DataLoader(train_data, batch_size=5, shuffle=True)

# --- 4. Load a pretrained ResNet18 ---
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
model.fc = nn.Linear(model.fc.in_features, 10)  # CIFAR-10 has 10 classes
model = model.to(device)

# --- 5. Loss and optimizer ---
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.01)

# --- 6. Training loop ---
epochs = 20  # train a few epochs
for epoch in range(epochs):
    model.train()
    running_loss = 0.0
    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()

    avg_loss = running_loss / len(train_loader)
    print(f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f}")

# --- 7. Test on the same 10 images ---
model.eval()
correct = 0
total = 0
with torch.no_grad():
    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        _, predicted = torch.max(outputs, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()

print(f"\n✅ Accuracy on 10 images: {100 * correct / total:.2f}%")
