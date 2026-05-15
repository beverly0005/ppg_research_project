#!/usr/bin/env python3
"""
tools/generate_sos.py
─────────────────────
Computes 3rd-order Butterworth bandpass SOS coefficients for the ESP32-S3
and prints them ready to paste into preprocessing.h.

Usage:
    pip install scipy numpy
    python tools/generate_sos.py
"""
import numpy as np
from scipy.signal import butter

FS   = 100.0    # Hz  (NEW_FREQUENCY)
LOW  = 0.5      # Hz
HIGH = 6.0      # Hz
ORD  = 3

nyq = 0.5 * FS
sos = butter(ORD, [LOW/nyq, HIGH/nyq], btype='band', output='sos')

print("// ── Paste into preprocessing.h  SOS_COEFF[][] ──────────────")
print(f"// butter({ORD}, [{LOW}/{nyq}, {HIGH}/{nyq}], btype='band', fs={FS})")
print(f"static const float SOS_COEFF[{len(sos)}][6] = {{")
for row in sos:
    b0,b1,b2,a0,a1,a2 = row
    assert abs(a0 - 1.0) < 1e-9, "a0 should be 1"
    print(f"    {{ {b0:.10f}f, {b1:.10f}f, {b2:.10f}f,"
          f"  1.0f, {a1:.10f}f, {a2:.10f}f }},")
print("};")

# Sanity-check: verify impulse response has energy in passband
from scipy.signal import sosfiltfilt, freqz_sos
w, h = freqz_sos(sos, worN=4096, fs=FS)
pb = (w >= LOW) & (w <= HIGH)
sb = (w <= LOW*0.5) | (w >= HIGH*2.0)
print(f"\nPassband gain ({LOW}–{HIGH} Hz): {np.abs(h[pb]).max():.4f}  (expect ~1.0)")
print(f"Stopband max  : {np.abs(h[sb]).max():.6f}  (expect << 1)")
