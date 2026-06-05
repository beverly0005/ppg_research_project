import numpy as np

def min_max_scaler(signal):
  sig_max = np.max(signal)
  sig_min = np.min(signal)
  return (signal - sig_min) / (sig_max - sig_min + 1e-6)

def right_pad_or_crop(signal, target_len=1500, pad_value=0.0):
    """
    Right-pad or right-crop a 1D signal to target_len.
    """
    signal = np.asarray(signal)

    if len(signal) >= target_len:
        return signal[:target_len]
    else:
        pad_width = target_len - len(signal)
        return np.pad(signal, (0, pad_width), mode="constant", constant_values=pad_value)