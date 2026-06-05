import numpy as np
from scipy.signal import find_peaks, resample
from scipy.optimize import curve_fit
from scipy.spatial.distance import cosine
from scipy.stats import skew, kurtosis
from pathlib import Path
import csv
import os
FS = 100
MIN_PULSE_LENGTH = 50  # Minimum samples for a valid pulse
MAX_PULSE_LENGTH = 1.5 * 100  # Maximum samples for a valid pulse (1.5s)

# @title
import traceback
def normalize_pulse(pulse):
    """Normalize pulse to [0, 1] range."""
    pulse_min = pulse.min()
    pulse_max = pulse.max()
    pulse_range = pulse_max - pulse_min

    if pulse_range < 1e-8:
        return None

    return (pulse - pulse_min) / pulse_range


def two_gaussian(t, H1, n1, W1, H2, n2, W2):
    """Two-Gaussian model for PPG pulse decomposition."""
    g1 = H1 * np.exp(-((t - n1) ** 2) / (2 * W1 ** 2 + 1e-8))
    g2 = H2 * np.exp(-((t - n2) ** 2) / (2 * W2 ** 2 + 1e-8))
    return g1 + g2


def fit_gaussian(pulse):
    """
    Fit two-Gaussian model to a normalized pulse (0-1 range, 50 samples).

    Returns: (H1, n1, W1, H2, n2, W2) or None if fitting fails
    """
    t = np.arange(len(pulse))
    n = len(pulse)

    # Find initial estimates from signal
    systolic_idx = np.argmax(pulse)
    systolic_height = pulse[systolic_idx]

    # Estimate diastolic region
    search_start = min(systolic_idx + 5, n - 5)
    search_end = min(systolic_idx + 35, n - 1)

    if search_end <= search_start:
        search_start = systolic_idx + 3
        search_end = n - 1

    search_region = pulse[search_start:search_end]

    # Find initial diastolic estimate
    if len(search_region) > 3:
        local_peaks, _ = find_peaks(search_region, distance=3)
        if len(local_peaks) > 0:
            peak_heights = search_region[local_peaks]
            best_peak = local_peaks[np.argmax(peak_heights)]
            diastolic_idx_init = search_start + best_peak
            diastolic_height_init = pulse[diastolic_idx_init]
        else:
            diastolic_idx_init = int(systolic_idx + 0.5 * (n - systolic_idx))
            diastolic_height_init = pulse[diastolic_idx_init]
    else:
        diastolic_idx_init = int(0.7 * n)
        diastolic_height_init = pulse[diastolic_idx_init]

    # Ensure diastolic is after systolic
    if diastolic_idx_init <= systolic_idx:
        diastolic_idx_init = min(systolic_idx + 10, n - 1)
        diastolic_height_init = pulse[diastolic_idx_init]

    # Initial parameter estimates
    p0 = [
        systolic_height,
        systolic_idx,
        5.0,
        max(diastolic_height_init, 0.1),
        diastolic_idx_init,
        5.0
    ]

    # Bounds
    bounds = (
        [0.5, 0, 2, 0.01, systolic_idx + 3, 2],
        [1.5, n * 0.5, 15, 0.8, n - 1, 15]
    )

    try:
        popt, _ = curve_fit(two_gaussian, t, pulse, p0=None, bounds=bounds, maxfev=3000)
        H1, n1, W1, H2, n2, W2 = popt

        # Validate: n2 should be clearly after n1
        if n2 <= n1 + 3:
            return None

        return (H1, n1, W1, H2, n2, W2)

    except Exception as e:
        print("Gaussian fitting failed for pulse. Returning None.", e)
        return None


def get_landmarks_from_gaussian(pulse, gaussian_params):
    """
    Extract landmarks using Gaussian parameters as guide.

    - idx_p1 = round(n1) → Systolic peak
    - idx_p2 = round(n2) → Diastolic peak
    - idx_notch = argmin between idx_p1 and idx_p2 (exclusive)
    """
    H1, n1, W1, H2, n2, W2 = gaussian_params
    n = len(pulse)

    # Systolic peak position from n1
    idx_p1 = int(np.clip(round(n1), 0, n - 1))

    # Diastolic peak position from n2
    idx_p2 = int(np.clip(round(n2), 0, n - 1))

    # Ensure idx_p2 > idx_p1
    if idx_p2 <= idx_p1:
        idx_p2 = min(idx_p1 + 5, n - 1)

    # Dicrotic notch: minimum btw sys and dia excluding endpoints
    if idx_p2 > idx_p1 + 2:
        search_segment = pulse[idx_p1 + 1 : idx_p2]  # Exclude both endpoints
        idx_notch = np.argmin(search_segment) + idx_p1 + 1
    else:
        # Peaks too close, estimate notch at midpoint
        idx_notch = (idx_p1 + idx_p2) // 2

    # Get values at landmarks
    val_p1 = pulse[idx_p1]
    val_p2 = pulse[idx_p2]
    val_notch = pulse[idx_notch]

    return {
        'idx_p1': idx_p1,
        'idx_p2': idx_p2,
        'idx_notch': idx_notch,
        'val_p1': val_p1,
        'val_p2': val_p2,
        'val_notch': val_notch
    }

def detect_valleys(signal, distance=FS*0.4):
    """Detect valleys (troughs) in the signal."""
    valleys, _ = find_peaks(-signal, distance=distance, prominence=0.1)
    return valleys

def extract_pulses_with_indices(signal, valleys):
    """
    Extract valley-to-valley segments with their original indices.

    Returns:
        pulses_normalized: List of normalized, resampled pulses
        pulse_metadata: List of dicts with valley_start, valley_end, original_length
    """
    pulses_normalized = []
    pulse_metadata = []

    for i in range(len(valleys) - 1):
        valley_start = valleys[i]
        valley_end = valleys[i + 1]
        original_length = valley_end - valley_start

        if MIN_PULSE_LENGTH <= original_length <= MAX_PULSE_LENGTH:
            pulse = signal[valley_start:valley_end]

            if np.any(np.isnan(pulse)):
                continue

            # pulse_resampled = resample(pulse, RESAMPLE_LENGTH)
            # pulse_normalized = normalize_pulse(pulse_resampled)
            pulse_normalized = normalize_pulse(pulse)
            if pulse_normalized is None:
                continue

            pulses_normalized.append(pulse_normalized)
            pulse_metadata.append({
                'valley_start': valley_start,
                'valley_end': valley_end,
                'original_pulse_length': original_length
            })

    return pulses_normalized, pulse_metadata


def compute_template(pulses):
    """Compute template as mean of all pulses."""
    if len(pulses) == 0:
        return None
    return np.mean(pulses, axis=0)


def compute_similarities(pulses, template):
    """Compute cosine similarity for each pulse to template."""
    if template is None:
        return [0.0] * len(pulses)

    similarities = []
    for pulse in pulses:
        similarity = 1 - cosine(pulse, template)
        similarities.append(similarity)

    return similarities


def valid_fit(pulse, gaussian_params):
  """
  Check that H1 > H2 and notch > valley
  """
  H1, n1, W1, H2, n2, W2 = gaussian_params
  n = len(pulse)

  landmarks = get_landmarks_from_gaussian(pulse, gaussian_params)
  idx_p1 = landmarks['idx_p1']
  idx_p2 = landmarks['idx_p2']
  idx_notch = landmarks['idx_notch']

  valid_H1 = H1 > H2
  valid_notch = landmarks['idx_notch'] < landmarks['val_p2']

  if valid_H1 and valid_notch:
    return True
  else:
    return False

def extract_key_features(pulse, gaussian_params):
    """
    Extract all 28 features from a normalized pulse using Gaussian-guided landmarks.

    Returns: dict of 28 features + validity flags
    """
    H1, n1, W1, H2, n2, W2 = gaussian_params
    n = len(pulse)

    # Get landmarks from Gaussian parameters
    landmarks = get_landmarks_from_gaussian(pulse, gaussian_params)
    idx_p1 = landmarks['idx_p1']
    idx_p2 = landmarks['idx_p2']
    idx_notch = landmarks['idx_notch']

    # ===== QUALITY FLAGS =====
    valid_h1_h2 = H1 > H2
    valid_notch = landmarks['val_notch'] < landmarks['val_p2']


    # # height features (3)
    highest_peak = landmarks['val_p1']
    dis_peak = landmarks['val_p2']
    notch = landmarks['val_notch']

    # # timing features (5)
    # time_notch = idx_notch
    # width_period = n  # Fixed at 50
    # td_peak_notch = idx_notch - idx_p1
    # td_notch_dia = idx_p2 - idx_notch
    # td_dia_end = n - idx_p2

    # # slope features (3)
    # if idx_p1 > 0:
    #     slop_rise = highest_peak / idx_p1
    # else:
    #     slop_rise = np.nan

    # time_to_end = n - idx_p1
    # if time_to_end > 0:
    #     slop_fall = (highest_peak - pulse[-1]) / time_to_end
    # else:
    #     slop_fall = np.nan

    # if idx_p2 > idx_p1:
    #     slop_peak_dia = (dis_peak - highest_peak) / (idx_p2 - idx_p1)
    # else:
    #     slop_peak_dia = np.nan

    # area features (5)
    # area_single = np.trapz(pulse)
    # area_start_max = np.trapz(pulse[:idx_p1 + 1]) if idx_p1 > 0 else 0
    # area_max_notch = np.trapz(pulse[idx_p1:idx_notch + 1])
    # area_notch_dia = np.trapz(pulse[idx_notch:idx_p2 + 1])
    # area_dia_end = np.trapz(pulse[idx_p2:])
    # sys_area = area_start_max + area_max_notch
    # dias_area = area_notch_dia + area_dia_end
    # auc = area_single

    # # spectral features (6)
    # fft_vals = np.fft.rfft(pulse)
    # psd = np.abs(fft_vals) ** 2
    # freqs = np.fft.rfftfreq(n, d=1.0)

    # psd_sum = np.sum(psd) + 1e-10
    # psd_norm = psd / psd_sum

    # f_mean = np.sum(freqs * psd_norm)
    # f_std = np.sqrt(np.sum(((freqs - f_mean) ** 2) * psd_norm))
    # f_energy = np.sum(psd)
    # f_entropy = -np.sum((psd_norm + 1e-10) * np.log2(psd_norm + 1e-10))
    # f_skew = skew(psd) if len(psd) > 2 else 0
    # f_kurt = kurtosis(psd) if len(psd) > 2 else 0

    return {
        # Quality flags
        'valid_h1_h2': valid_h1_h2,
        'valid_notch': valid_notch,
        # Gaussian features (6)
        'H1': H1, 'H2': H2, 'n1': n1, 'n2': n2, 'W1': W1, 'W2': W2, 'idx_p1': idx_p1, 'idx_p2': idx_p2, 'idx_notch': idx_notch,
        # # Height features (3)
        'highest_peak': highest_peak, 'dis_peak': dis_peak, 'notch': notch,
        # # Timing features (5)
        # 'time_notch': time_notch, #'width_period': width_period,
        # 'td_peak_notch': td_peak_notch, 'td_notch_dia': td_notch_dia, 'td_dia_end': td_dia_end,
        # # Slope features (3)
        # 'slop_rise': slop_rise, 'slop_fall': slop_fall, 'slop_peak_dia': slop_peak_dia,
        # Area features (5)
        # 'area_single': area_single, 'area_start_max': area_start_max,
        # 'area_max_notch': area_max_notch, 'area_notch_dia': area_notch_dia, 'area_dia_end': area_dia_end,
        # 'sys_area': sys_area, 'dias_area': dias_area, 'auc': auc,
        # # Spectral features (6)
        # 'f_mean': f_mean, 'f_std': f_std, 'f_energy': f_energy,
        # 'f_entropy': f_entropy, 'f_skew': f_skew, 'f_kurt': f_kurt
    }

def chunk_list(lst, window_size=15, step=14):
    return [
        lst[i:i + window_size:step]
        for i in range(0, len(lst) - window_size + 1, step)
    ]

def process_single_file(filepath, glucose_value):
    """
    Process a single 16-min filtered PPG file.
    Returns list of feature dictionaries (one per valid pulse).
    """
    try:
        signal = np.load(filepath)
        valleys = detect_valleys(signal)
        # csv_path = '/content/drive/MyDrive/2025_PPG_GLUC/Data/100Hz_ppg_features_1min_cleanV2_15pulses.csv'

        # chunks = chunk_list(valleys, 15)

        # df = pd.DataFrame(chunks)
        # df.columns = ['seg_start', 'seg_end']

        # split_filepath = filepath.split('/')
        # window = (split_filepath[-1]).split('_')[6]

        if len(valleys) < 2:
            return []

        # Extract pulses with their original indices
        pulses, pulse_metadata = extract_pulses_with_indices(signal, valleys)

        # print("Len pulses: ", len(pulses), " Len metadata: ", len(pulse_metadata))

        if len(pulses) == 0:
            return []

        # Compute template and similarities
        # template = compute_template(pulses)
        # similarities = compute_similarities(pulses, template)
        # print(similarities)
        # Filter by similarity threshold
        # filtered_indices = [i for i, sim in enumerate(similarities) if sim >= SIMILARITY_THRESHOLD]

        # if len(filtered_indices) == 0:
            # return []

        # Parse filename
        filename = Path(filepath).stem
        parts = filename.split('_')
        caseid = parts[1]
        glucose_time = parts[3]

        # Extract features for each valid pulse
        results = []

        for seg_idx, pulse in enumerate(pulses):
            # pulse = pulses[orig_idx]
            meta = pulse_metadata[seg_idx]
            # similarity = similarities[orig_idx]

            # Fit Gaussian
            gaussian_params = fit_gaussian(pulse)
            # print(gaussian_params)
            if gaussian_params is None:
                continue

            # Extract features (Not required here)
            features = extract_key_features(pulse, gaussian_params)

            # Add metadata
            features['caseid'] = caseid
            features['glucose_time'] = glucose_time
            features['glucose_value'] = glucose_value
            features['segment_index'] = seg_idx
            features['total_segments'] = len(pulses)
            features['valley_start'] = meta['valley_start']
            features['valley_end'] = meta['valley_end']
            features['original_pulse_length'] = meta['original_pulse_length']
            # features['cosine_similarity'] = similarity

            results.append(features)

        # print(len(results))
        # df["caseid"] = caseid
        # df["glucose_time"] = glucose_time
        # df['window'] = window
        # df["glucose"] = glucose_value
        # Append without overwriting
        # df.to_csv(
        #   csv_path,
        #   mode="a",                    # append
        #   header=not os.path.exists(csv_path),  # write header only once
        #   index=False
        # )
        return results

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        traceback.print_exc()
        return []
    

def find_segments(signal):
    """
    Process a single filtered PPG.
    Returns list of feature dictionaries (one per valid pulse).
    """
    try:
        valleys = detect_valleys(signal)

        if len(valleys) < 2:
            return []

        # Extract pulses with their original indices
        pulses, pulse_metadata = extract_pulses_with_indices(signal, valleys)

        # print("Len pulses: ", len(pulses), " Len metadata: ", len(pulse_metadata))

        if len(pulses) == 0:
            return []

        # Extract features for each valid pulse
        results = []

        for seg_idx, pulse in enumerate(pulses):
            # pulse = pulses[orig_idx]
            meta = pulse_metadata[seg_idx]
            # similarity = similarities[orig_idx]

            # Fit Gaussian
            gaussian_params = fit_gaussian(pulse)
            # print(gaussian_params)
            if gaussian_params is None:
                continue

            # Extract features (Not required here)
            features = extract_key_features(pulse, gaussian_params)

            # Add metadata
            features['segment_index'] = seg_idx
            features['total_segments'] = len(pulses)
            features['valley_start'] = meta['valley_start']
            features['valley_end'] = meta['valley_end']
            features['original_pulse_length'] = meta['original_pulse_length']
            # features['cosine_similarity'] = similarity

            results.append(features)

        return results

    except Exception as e:
        print(f"Error processing {signal}: {e}")
        traceback.print_exc()
        return []