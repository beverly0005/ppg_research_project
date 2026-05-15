#!/usr/bin/env python3
"""
tools/convert_model.py
──────────────────────
Converts best_model.pt → best_model.tflite → model_data.h

SETUP (run once):
    pip install litert-torch torch onnxscript onnx onnxsim onnx-tf tensorflow

  - 'ai-edge-torch' was renamed to 'litert-torch' — update your venv:
        pip uninstall ai-edge-torch -y
        pip install litert-torch

ROUTE 1 (litert-torch)  ← tried first, cleanest, no missing-op issues
ROUTE 2 (ONNX fallback) ← used if litert-torch fails; needs onnxscript
"""
import argparse, subprocess, sys, os, re
import numpy as np
import torch

parser = argparse.ArgumentParser()
parser.add_argument("--pt",     default="best_model.pt")
parser.add_argument("--tflite", default="best_model.tflite")
parser.add_argument("--header", default="main/model_data.h")
args = parser.parse_args()

# ── Load model ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from multimodal_model import MultiModalModel

model = MultiModalModel()
model.load_state_dict(torch.load(args.pt, map_location="cpu"))
model.eval()
print(f"[PT] Loaded {args.pt}")

# Dummy inputs — must be a flat tuple (no keyword args)
x    = torch.randn(1, 1, 1500)
mask = torch.ones(1, 1, 1500)
demo = torch.randn(1, 8)
sample_inputs = (x, mask, demo)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 1: litert-torch  (renamed from ai-edge-torch)
# ─────────────────────────────────────────────────────────────────────────────
converted = False
try:
    import litert_torch
    print("[ROUTE1] litert-torch found, converting ...")
    edge_model = litert_torch.convert(model, sample_inputs)
    edge_model.export(args.tflite)
    print(f"[ROUTE1] Success → {args.tflite}")
    converted = True
except ImportError:
    print("[ROUTE1] litert-torch not installed.")
    print("         Run: pip uninstall ai-edge-torch -y && pip install litert-torch")
except Exception as e:
    print(f"[ROUTE1] Failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE 2: ONNX → onnxsim → TF SavedModel → TFLite
#
# torch.onnx.export now requires onnxscript:
#   pip install onnxscript
# ─────────────────────────────────────────────────────────────────────────────
if not converted:
    print("\n[ROUTE2] Trying ONNX route ...")

    onnx_path     = args.tflite.replace(".tflite", "_raw.onnx")
    onnx_sim_path = args.tflite.replace(".tflite", "_sim.onnx")
    tf_path       = args.tflite.replace(".tflite", "_saved_model")

    # Step 1: Export ONNX
    # opset 16 is the sweet spot: modern enough for good coverage,
    # old enough not to generate excessive control-flow ops.
    print("[ROUTE2] Exporting ONNX (opset 16) ...")
    try:
        torch.onnx.export(
            model,
            sample_inputs,
            onnx_path,
            input_names  = ["signal", "mask", "demo"],
            output_names = ["glucose"],
            dynamic_axes = {},       # fixed shapes — important for TFLite Micro
            opset_version= 16,
            verbose      = False,
        )
        print(f"[ROUTE2] ONNX saved → {onnx_path}")
    except ModuleNotFoundError as e:
        print(f"\n[ROUTE2] Missing dependency: {e}")
        print("         Run: pip install onnxscript")
        sys.exit(1)

    # Step 2: Simplify with onnxsim (folds constants, removes dead branches)
    try:
        import onnx, onnxsim
        model_sim, ok = onnxsim.simplify(onnx.load(onnx_path))
        if ok:
            onnx.save(model_sim, onnx_sim_path)
            onnx_to_convert = onnx_sim_path
            print(f"[ROUTE2] Simplified → {onnx_sim_path}")
        else:
            print("[ROUTE2] Simplification had no effect, using original")
            onnx_to_convert = onnx_path
    except ImportError:
        print("[ROUTE2] onnxsim not installed (pip install onnxsim), skipping simplification")
        import onnx
        onnx_to_convert = onnx_path

    # Step 3: ONNX → TF SavedModel
    print("[ROUTE2] Converting ONNX → TF SavedModel ...")
    try:
        from onnx_tf.backend import prepare
        tf_rep = prepare(onnx.load(onnx_to_convert))
        tf_rep.export_graph(tf_path)
        print(f"[ROUTE2] SavedModel → {tf_path}")
    except ImportError:
        print("[ROUTE2] onnx-tf not installed. Run: pip install onnx-tf")
        sys.exit(1)

    # Step 4: TF SavedModel → TFLite (builtins only — no Flex delegate)
    print("[ROUTE2] Converting TF SavedModel → TFLite ...")
    import tensorflow as tf
    converter = tf.lite.TFLiteConverter.from_saved_model(tf_path)
    converter.optimizations = []
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
    converter.experimental_new_converter = True

    try:
        tflite_model = converter.convert()
    except Exception as e:
        print(f"\n[ROUTE2] TFLite conversion failed: {e}")
        print("\nThe model contains an op that can't be expressed as TFLite builtins.")
        print("Run: python tools/find_select_ops.py --pt", args.pt)
        sys.exit(1)

    with open(args.tflite, "wb") as f:
        f.write(tflite_model)
    print(f"[ROUTE2] TFLite saved → {args.tflite}  ({len(tflite_model)//1024} KB)")
    converted = True

# ─────────────────────────────────────────────────────────────────────────────
# Generate model_data.h
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[HDR] Generating {args.header} ...")
result = subprocess.run(["xxd", "-i", args.tflite], capture_output=True, text=True)
header = result.stdout

# Rename xxd's auto-generated variable name to g_model_data
header = re.sub(r'unsigned char \w+\s*\[\]', 'const unsigned char g_model_data[]', header)
header = re.sub(r'unsigned int\s+\w+',       'const unsigned int  g_model_data_len', header)
header = "#pragma once\n\n" + header

os.makedirs(os.path.dirname(os.path.abspath(args.header)) or ".", exist_ok=True)
with open(args.header, "w") as f:
    f.write(header)
print(f"[HDR] Written → {args.header}")

# ─────────────────────────────────────────────────────────────────────────────
# Quick sanity check using TFLite Python runtime
# ─────────────────────────────────────────────────────────────────────────────
print("\n[CHECK] Running inference sanity check ...")
import tensorflow as tf

interp = tf.lite.Interpreter(model_path=args.tflite)
interp.allocate_tensors()
inp = interp.get_input_details()
out = interp.get_output_details()

print("[CHECK] Inputs:")
for d in inp:
    print(f"          [{d['index']}] {d['name']:<30} shape={d['shape'].tolist()}")
print(f"[CHECK] Output: {out[0]['name']}  shape={out[0]['shape'].tolist()}")

# Feed by index order (signal=0, mask=1, demo=2) — verify against input log above
interp.set_tensor(inp[0]['index'], x.numpy())
interp.set_tensor(inp[1]['index'], mask.numpy())
interp.set_tensor(inp[2]['index'], demo.numpy())
interp.invoke()
tfl_out = float(interp.get_tensor(out[0]['index'])[0])

with torch.no_grad():
    pt_out = float(model(x, m=mask, d=demo).squeeze())

print(f"[CHECK] PyTorch output : {pt_out:.6f}")
print(f"[CHECK] TFLite  output : {tfl_out:.6f}")
print(f"[CHECK] Absolute error : {abs(pt_out - tfl_out):.2e}")
if abs(pt_out - tfl_out) < 0.01:
    print("[CHECK] PASSED ✓")
else:
    print("[CHECK] WARNING: outputs differ by more than 0.01 — check conversion")

print(f"""
Done.
Next steps:
  1. Copy {args.header} into your esp32_glucose/main/ folder
  2. Run: python tools/list_tflite_ops.py {args.tflite}
     and verify all ops are in build_resolver() in model_runner.h
  3. idf.py build && idf.py -p /dev/cu.usbmodem1101 flash monitor
""")