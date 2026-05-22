import numpy as np
import torch
import joblib
import math
from multimodal_model import MultiModalModel

# 1. Configuration & Constants
MODEL_PATH = "best_model.pt"
SCALER_PATH = "scaler.pkl"  # The scikit-learn scaler we verified

NUM_SEGMENTS = 15
SEG_LEN = 100
SIGNAL_LEN = NUM_SEGMENTS * SEG_LEN  # 1500

# 2. Replicate the C++ Synthetic Data Generation Exactly
print("[PYTHON] Generating synthetic test inputs matching C++ exactly...")

test_signal = np.zeros(SIGNAL_LEN, dtype=np.float32)
test_mask = np.zeros(SIGNAL_LEN, dtype=np.float32)

for seg in range(NUM_SEGMENTS):
    real_len = 80
    for i in range(SEG_LEN):
        idx = seg * SEG_LEN + i
        if i < real_len:
            t = float(i) / real_len
            # Replicates: 0.5f + 0.5f * sinf(t * 6.283f)
            test_signal[idx] = 0.5 + 0.5 * math.sin(t * 6.283)
            test_mask[idx] = 1.0
        else:
            test_signal[idx] = 0.0
            test_mask[idx] = 0.0

# 3. Construct the Demographic Vector
# In your C++ code, the array is defined as:
# [age, sex, height, weight, bmi, actual_hr, preop_htn, preop_dm]
# We must scale the continuous variables using the scaler's parameters.

print("[PYTHON] Loading scaler to preprocess demographics...")
scaler = joblib.load(SCALER_PATH)

# Raw unscaled values representing the "training mean" (which results in 0.0 after transform)
# Hand-coding the exact means from the scaler to match the C++ 0.0f baseline
raw_age = 55.20598752
raw_weight = 64.63251729
raw_bmi = 23.50403947
raw_height = 165.37427053
raw_actual_hr = 80.61671435

# Binary features are NOT passed through the StandardScaler
raw_sex = 1.0        # Male
raw_preop_htn = 0.0
raw_preop_dm = 0.0

# Shape continuous features into the 2D format scikit-learn expects: [[age, weight, bmi, height, actual_hr]]
continuous_features = np.array([[raw_age, raw_weight, raw_bmi, raw_height, raw_actual_hr]], dtype=np.float32)
scaled_continuous = scaler.transform(continuous_features)[0]

# Reassemble the final demographic array in the exact layout your PyTorch model expects.
# (Verify this layout against your multimodal_model.py's forward pass input layout)
test_demo = np.array([
    scaled_continuous[0], # age (scaled -> 0.0)
    raw_sex,              # sex (binary -> 1.0)
    scaled_continuous[3], # height (scaled -> 0.0)
    scaled_continuous[1], # weight (scaled -> 0.0)
    scaled_continuous[2], # bmi (scaled -> 0.0)
    scaled_continuous[4], # actual_hr (scaled -> 0.0)
    raw_preop_htn,        # preop_htn (binary -> 0.0)
    raw_preop_dm          # preop_dm (binary -> 0.0)
], dtype=np.float32)

# 4. Prepare Tensors for PyTorch (Add Batch Dimension)
# PyTorch models expect shapes like (batch_size, sequence_length) or (batch_size, num_features)
signal_tensor = torch.tensor(test_signal, dtype=torch.float32).unsqueeze(0).unsqueeze(0) # Shape: (1, 1, 1500)
mask_tensor = torch.tensor(test_mask, dtype=torch.float32).unsqueeze(0).unsqueeze(0)     # Shape: (1, 1, 1500)
demo_tensor = torch.tensor(test_demo, dtype=torch.float32).unsqueeze(0)     # Shape: (1, 8)

# 5. Load Model and Run Inference
print(f"[PYTHON] Loading PyTorch model from {MODEL_PATH}...")
# Note: If your multimodal_model.py requires the class definition to load, 
# make sure to import it at the top, e.g., `from multimodal_model import MultimodalModel`
# If best_model.pt is a weights-only state_dict, instantiate your model architecture first:
model = MultiModalModel()
model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device('cpu')))

# try:
#     # Attempting to load as a fully serialized model object
#     model = torch.load(MODEL_PATH, map_location=torch.device('cpu'))
# except Exception:
#     print("[WARNING] Direct torch.load failed. Ensure your class definitions are imported if it's a state_dict.")
#     raise

model.eval()

print("[PYTHON] Running inference...")
with torch.no_grad():
    # Pass inputs matching your multimodal_model.py forward() signature
    # Example assumes: forward(signal, mask, demo)
    prediction = model(signal_tensor, mask_tensor, demo_tensor)
    
    # Extract the scalar prediction value
    if isinstance(prediction, torch.Tensor):
        pred_val = prediction.item()
    else:
        # If your model returns a tuple or dictionary, adjust accordingly
        pred_val = prediction[0].item()

print("\n" + "="*40)
print(f"[SUCCESS] Python PyTorch Inference Completed")
print(f"Prediction Output: {pred_val:.4f} mg/dL")
print("="*40)
print("Compare this exact float value against your ESP32 [SELFTEST] Prediction output.")
print("They should match exceptionally close (minor variances are normal due to float precision differences on architectures).")