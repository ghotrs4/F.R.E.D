"""
local_classifier.py
Importable wrapper around the locally trained Food-101 ResNet18 model.
Lazy-loads the model on first call so import is cheap.
"""

import os
import torch
import torch.nn as nn
import torchvision.transforms as transforms
from torchvision import models
from PIL import Image

# Paths are resolved relative to this file so they work regardless of cwd
_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_BASE_DIR, 'food_classifier_20260404_211058.pth')
_META_PATH  = os.path.join(_BASE_DIR, 'data', 'food-101', 'meta', 'classes.txt')

# Image transform – must match training exactly
_TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    )
])

# Lazy state
_device      = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
_model       = None
_class_names = None
_load_error  = None

_LABEL_ALIASES = {
    'bellpepper': 'bell pepper',
}


def _format_label(raw_label):
    """Convert raw class labels to readable text for API responses."""
    label = str(raw_label).strip().replace('_', ' ').replace('-', ' ')
    condensed = label.replace(' ', '').lower()
    if condensed.startswith('rotten') and len(condensed) > len('rotten'):
        return f"rotten {condensed[len('rotten'):]}"
    if condensed in _LABEL_ALIASES:
        return _LABEL_ALIASES[condensed]
    return label


def _load_class_names():
    """Load Food-101 class names from the dataset metadata file if present."""
    if os.path.exists(_META_PATH):
        with open(_META_PATH) as f:
            return [line.strip() for line in f if line.strip()]
    # Fallback: alphabetically ordered Food-101 classes (matches torchvision index)
    return [
        "apple_pie", "baby_back_ribs", "baklava", "beef_carpaccio", "beef_tartare",
        "beet_salad", "beignets", "bibimbap", "bread_pudding", "breakfast_burrito",
        "bruschetta", "caesar_salad", "cannoli", "caprese_salad", "carrot_cake",
        "ceviche", "cheesecake", "cheese_plate", "chicken_curry", "chicken_quesadilla",
        "chicken_wings", "chocolate_cake", "chocolate_mousse", "churros", "clam_chowder",
        "club_sandwich", "crab_cakes", "creme_brulee", "croque_madame", "cup_cakes",
        "deviled_eggs", "donuts", "dumplings", "edamame", "eggs_benedict",
        "escargots", "falafel", "filet_mignon", "fish_and_chips", "foie_gras",
        "french_fries", "french_onion_soup", "french_toast", "fried_calamari", "fried_rice",
        "frozen_yogurt", "garlic_bread", "gnocchi", "greek_salad", "grilled_cheese_sandwich",
        "grilled_salmon", "guacamole", "gyoza", "hamburger", "hot_and_sour_soup",
        "hot_dog", "huevos_rancheros", "hummus", "ice_cream", "lasagna",
        "lobster_bisque", "lobster_roll_sandwich", "macaroni_and_cheese", "macarons", "miso_soup",
        "mussels", "nachos", "omelette", "onion_rings", "oysters",
        "pad_thai", "paella", "pancakes", "panna_cotta", "peking_duck",
        "pho", "pizza", "pork_chop", "poutine", "prime_rib",
        "pulled_pork_sandwich", "ramen", "ravioli", "red_velvet_cake", "risotto",
        "samosa", "sashimi", "scallops", "seaweed_salad", "shrimp_and_grits",
        "spaghetti_bolognese", "spaghetti_carbonara", "spring_rolls", "steak", "strawberry_shortcake",
        "sushi", "tacos", "takoyaki", "tiramisu", "tuna_tartare", "waffles",
    ]


def _ensure_loaded():
    """Load the model once; cache errors so we don't retry on every call."""
    global _model, _class_names, _load_error
    if _model is not None:
        return True
    if _load_error is not None:
        return False
    try:
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(f"Model file not found: {_MODEL_PATH}")
        class_names = _load_class_names()
        checkpoint = torch.load(_MODEL_PATH, map_location=_device)

        # Support both raw state_dict checkpoints and wrapped training checkpoints.
        state_dict = checkpoint
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
            if isinstance(checkpoint.get('class_names'), list) and checkpoint['class_names']:
                class_names = checkpoint['class_names']

        num_classes = len(class_names)
        if isinstance(checkpoint, dict) and isinstance(checkpoint.get('num_classes'), int):
            num_classes = checkpoint['num_classes']

        m = models.resnet18(weights=None)
        m.fc = nn.Linear(m.fc.in_features, num_classes)
        m.load_state_dict(state_dict)
        m.to(_device)
        m.eval()
        _model       = m
        _class_names = class_names
        return True
    except Exception as exc:
        _load_error = str(exc)
        return False


def is_available():
    """Return True if the model loaded successfully."""
    return _ensure_loaded()


def predict(pil_image):
    """
    Run inference on a PIL Image.

    Returns a dict:
      {
        "predicted_class": str,        # human-readable, spaces not underscores
        "confidence":      float,      # 0–100
        "top5": [
          {"class": str, "confidence": float},
          ...
        ]
      }

    Raises RuntimeError if the model could not be loaded.
    """
    if not _ensure_loaded():
        raise RuntimeError(f"Local model unavailable: {_load_error}")

    tensor = _TRANSFORM(pil_image.convert('RGB')).unsqueeze(0).to(_device)

    with torch.no_grad():
        output = _model(tensor)
        probs  = torch.softmax(output, 1)[0]
        conf, idx = torch.max(probs, 0)
        top5_prob, top5_idx = torch.topk(probs, 5)

    return {
        'predicted_class': _format_label(_class_names[idx.item()]),
        'confidence':      round(conf.item() * 100, 2),
        'top5': [
            {
                'class':      _format_label(_class_names[i.item()]),
                'confidence': round(p.item() * 100, 2),
            }
            for i, p in zip(top5_idx, top5_prob)
        ],
    }
