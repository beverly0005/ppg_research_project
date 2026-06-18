from scipy.signal import butter, filtfilt, find_peaks
from scipy.interpolate import CubicSpline
import numpy as np

def invert_signal(signal):
    signals = np.array(signal)
    mean_signal = signals.mean()
    inverted_signals = 2 * mean_signal - signals
    return inverted_signals

def butter_lowpass_filter(data, cutoff, fs, order=3):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    y = filtfilt(b, a, data)
    return y

def detect_valleys_ppg(signal, fs=100):
    """Detects valleys (feet) of PPG pulses."""
    inverted_signal = -signal # inverting these signals to find valleys as peaks. Do not use the invert_signal() function here.
    valleys, _ = find_peaks(inverted_signal, distance=fs*0.4, prominence=0.1)
    if len(valleys) < 2:
        return np.array([0, len(signal)-1])
    return valleys

def spline_baseline_remove(signal, fs=100):
    """Removes baseline drift using Cubic Spline on valleys."""
    valleys = detect_valleys_ppg(signal, fs)
    xk = valleys
    yk = signal[valleys]
    try:
        cs = CubicSpline(xk, yk, bc_type='natural')
        baseline = cs(np.arange(len(signal)))
        return signal - baseline
    except:
        return signal - np.mean(signal)