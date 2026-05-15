#!/usr/bin/env python3
"""
tools/compare_models.py
───────────────────────
Compares the output of:
  1. Original .pt  (PyTorch, mode="nearest" after the fix)
  2. .tflite file  (converted model loaded via TFLite Python runtime)

across N random inputs and reports max/mean absolute error so you can
confirm the conversion is numerically faithful before flashing.

Usage:
    pip install torch tensorflow numpy
    python tools/compare_models.py \\
        --pt   best_model.pt \\
        --tflite best_model.tflite \\
        --n    100

The script also optionally tests with real preprocessed signals if you
have a waveform_u1.csv in the current directory.
"""
import argparse, sys, os
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--pt",      default="best_model.pt",      help="PyTorch weights file")
parser.add_argument("--tflite",  default="best_model.tflite",  help="TFLite model file")
parser.add_argument("--n",       type=int, default=50,          help="Number of random test inputs")
parser.add_argument("--csv",     default=None,                  help="Optional waveform_u1.csv for real-data test")
parser.add_argument("--tol",     type=float, default=0.05,      help="Max acceptable absolute error (mmol/L)")
args = parser.parse_args()

# ── Load PyTorch model ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import torch
from multimodal_model import MultiModalModel   # fixed version (mode="nearest")

pt_model = MultiModalModel()
pt_model.load_state_dict(torch.load(args.pt, map_location="cpu"))
pt_model.eval()
print(f"[PT] Loaded {args.pt}")

# ── Load TFLite model ─────────────────────────────────────────────────────────
import tensorflow as tf

interp = tf.lite.Interpreter(model_path=args.tflite)
interp.allocate_tensors()
inp_det = interp.get_input_details()
out_det = interp.get_output_details()

print(f"[TFL] Loaded {args.tflite}")
print(f"[TFL] Inputs:")
for d in inp_det:
    print(f"        [{d['index']}] {d['name']}  shape={d['shape'].tolist()}  dtype={d['dtype'].__name__}")
print(f"[TFL] Output: {out_det[0]['name']}  shape={out_det[0]['shape'].tolist()}")
print()

# ── Helper: run one TFLite inference ─────────────────────────────────────────
def tflite_infer(signal, mask, demo):
    """
    signal, mask: np.float32 (1, 1, 1500)
    demo        : np.float32 (1, 8)
    Returns float scalar.
    
    Input order is determined by tensor index, not name.
    Adjust the set_tensor calls if your model has a different input order
    (visible in the [TFL] Inputs printout above).
    """
    # Map by shape to handle any input ordering
    for d in inp_det:
        shape = d['shape'].tolist()
        if shape == [1, 1, 1500] and 'signal' in d['name'].lower():
            interp.set_tensor(d['index'], signal)
        elif shape == [1, 1, 1500] and 'mask' in d['name'].lower():
            interp.set_tensor(d['index'], mask)
        elif shape == [1, 8]:
            interp.set_tensor(d['index'], demo)
        else:
            # Fallback: assign by index order (signal=0, mask=1, demo=2)
            if d['index'] == inp_det[0]['index']:
                interp.set_tensor(d['index'], signal)
            elif d['index'] == inp_det[1]['index']:
                interp.set_tensor(d['index'], mask)
            else:
                interp.set_tensor(d['index'], demo)

    interp.invoke()
    return float(interp.get_tensor(out_det[0]['index'])[0])


# ── Helper: run one PyTorch inference ────────────────────────────────────────
def pt_infer(signal_np, mask_np, demo_np):
    with torch.no_grad():
        x = torch.tensor(signal_np)
        m = torch.tensor(mask_np)
        d = torch.tensor(demo_np)
        return float(pt_model(x, m=m, d=d).squeeze())


# ── Random input tests ────────────────────────────────────────────────────────
print(f"Running {args.n} random input tests ...")
errors = []

# Use demographically plausible demo feature ranges
# [age, sex, height, weight, bmi, actual_hr, preop_htn, preop_dm]
# (already StandardScaler-normalised, so use ~N(0,1) range)
rng = np.random.default_rng(42)

for i in range(args.n):
    # Random normalised signal with a realistic mask (70-100% real samples)
    real_len   = rng.integers(1050, 1501)    # 70–100% of 1500
    signal_raw = rng.standard_normal((1, 1, 1500)).astype(np.float32)
    mask_raw   = np.zeros((1, 1, 1500), dtype=np.float32)
    mask_raw[0, 0, :real_len] = 1.0

    # Random scaled demographics
    demo_raw = rng.standard_normal((1, 8)).astype(np.float32)
    # Force binary features (sex, htn, dm) to 0 or 1
    demo_raw[0, 1] = float(rng.integers(0, 2))
    demo_raw[0, 6] = float(rng.integers(0, 2))
    demo_raw[0, 7] = float(rng.integers(0, 2))

    pt_out  = pt_infer(signal_raw, mask_raw, demo_raw)
    tfl_out = tflite_infer(signal_raw, mask_raw, demo_raw)
    err     = abs(pt_out - tfl_out)
    errors.append(err)

    if (i + 1) % 10 == 0:
        print(f"  {i+1:3d}/{args.n}  max_err_so_far={max(errors):.6f}")

errors = np.array(errors)
print()
print("=" * 50)
print(f"Random input test results ({args.n} samples):")
print(f"  Max absolute error  : {errors.max():.6f} mmol/L")
print(f"  Mean absolute error : {errors.mean():.6f} mmol/L")
print(f"  Std of errors       : {errors.std():.6f} mmol/L")
passed = errors.max() < args.tol
print(f"  Tolerance ({args.tol} mmol/L): {'PASSED ✓' if passed else 'FAILED ✗'}")
print("=" * 50)

# ── Real CSV test (optional) ──────────────────────────────────────────────────
if args.csv and os.path.exists(args.csv):
    print(f"\nRunning real-data test from {args.csv} ...")
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        import pandas as pd
        from scipy.signal import resample
        # Import preprocessing pipeline
        sys.path.insert(0, "..")
        # We'll do a minimal version here since filtering_spline.py may not be present
        raw = pd.read_csv(args.csv)["signal"].values.astype(np.float32)
        raw = -raw   # invert

        OLD_FS, NEW_FS = 40.5, 100.0
        resampled = resample(raw, int(len(raw) * NEW_FS / OLD_FS)).astype(np.float32)

        # Build a simple signal: truncate/pad to 1500, normalise
        sig = resampled[:1500] if len(resampled) >= 1500 else np.pad(resampled, (0, 1500-len(resampled)))
        sig = (sig - sig.min()) / (sig.max() - sig.min() + 1e-8)
        real_len = min(len(resampled), 1500)

        signal_np = sig.reshape(1, 1, 1500).astype(np.float32)
        mask_np   = np.zeros((1, 1, 1500), dtype=np.float32)
        mask_np[0, 0, :real_len] = 1.0
        demo_np   = np.zeros((1, 8), dtype=np.float32)  # placeholder demographics

        pt_out  = pt_infer(signal_np, mask_np, demo_np)
        tfl_out = tflite_infer(signal_np, mask_np, demo_np)
        print(f"  PyTorch output  : {pt_out:.4f} mmol/L")
        print(f"  TFLite  output  : {tfl_out:.4f} mmol/L")
        print(f"  Absolute error  : {abs(pt_out - tfl_out):.6f} mmol/L")
    except Exception as e:
        print(f"  Real-data test failed: {e}")
else:
    if args.csv:
        print(f"\n[SKIP] {args.csv} not found — skipping real-data test")

print("\nDone.")
if not passed:
    print("WARNING: errors exceed tolerance. Check that:")
    print("  1. multimodal_model.py uses mode='nearest' (not 'area')")
    print("  2. The same .pt file was used for both PyTorch and conversion")
    print("  3. The model is in eval() mode (no Dropout randomness)")
    sys.exit(1)
