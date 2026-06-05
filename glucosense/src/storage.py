import os
import csv
import pandas as pd
from datetime import datetime

# Resolve directories relative to the ROOT of the project, not the core folder
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "recordings")
CALIBRATIONS_FILE = os.path.join(PROJECT_ROOT, "calibrations.csv")

os.makedirs(RECORDINGS_DIR, exist_ok=True)

def load_calibration(name: str) -> float | None:
    if not name.strip() or not os.path.exists(CALIBRATIONS_FILE):
        return None
    try:
        df = pd.read_csv(CALIBRATIONS_FILE)
        match = df[df["name"].str.lower() == name.strip().lower()]
        if not match.empty:
            return float(match.iloc[-1]["calibration_mgdl"])
    except Exception:
        pass
    return None

def save_calibration(name: str, actual_mgdl: float, predicted_mgdl: float):
    if not name.strip():
        return
    offset_mgdl = actual_mgdl - predicted_mgdl
    file_exists = os.path.exists(CALIBRATIONS_FILE)
    next_id = 1
    if file_exists:
        try:
            df = pd.read_csv(CALIBRATIONS_FILE)
            next_id = int(df["id"].max()) + 1 if not df.empty else 1
        except Exception:
            pass
    with open(CALIBRATIONS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["id", "name", "calibration_mgdl"])
        writer.writerow([next_id, name.strip(), round(offset_mgdl, 2)])

def slugify_name(name: str) -> str:
    import re
    name = name.strip().lower()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name or "unknown"

def get_next_recording_id() -> int:
    ids = []
    for fname in os.listdir(RECORDINGS_DIR):
        if fname.endswith(".csv"):
            try: ids.append(int(fname.split("_")[0]))
            except ValueError: pass
    return max(ids, default=0) + 1

def save_recording_csv(
    patient_name: str,
    demographics: dict,
    timestamps: list,
    raw_signal: list,
    u2_vitals: list,
    prediction: float | None,
    calibrated_glucose: float | None,
    recording_datetime: datetime,
    actual_glucose: float | None = None,
    time_meal: str = "",
    meal_state: str = "", 
    finger_prick_location: str = "",   
    finger_sensor_location: str = "",  
    remarks: str = "",
) -> str:
    slug = slugify_name(patient_name)
    rec_id = get_next_recording_id()
    dt_str = recording_datetime.strftime("%Y-%m-%d_%H-%M-%S")
    filepath = os.path.join(RECORDINGS_DIR, f"{rec_id:04d}_{slug}_{dt_str}.csv")
    bmi = demographics["weight"] / (demographics["height"] / 100) ** 2

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["# recording_id", rec_id])
        writer.writerow(["# patient_name", patient_name.strip()])
        writer.writerow(["# recorded_at", recording_datetime.strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(["# time_meal", time_meal.strip() if time_meal.strip() else "N/A"])
        writer.writerow(["# meal_state", meal_state]) 
        
        # New Finger Locations
        writer.writerow(["# finger_prick_location", finger_prick_location.lower().replace(" ", "_") if finger_prick_location else "N/A"])
        writer.writerow(["# finger_sensor_location", finger_sensor_location.lower().replace(" ", "_") if finger_sensor_location else "N/A"])
        
        # Biometrics
        writer.writerow(["# race", demographics.get("race", "N/A")]) 
        writer.writerow(["# age", demographics["age"]])
        writer.writerow(["# sex", "Male" if demographics["sex"] == 1 else "Female"])
        writer.writerow(["# height_cm", demographics["height"]])
        writer.writerow(["# weight_kg", demographics["weight"]])
        writer.writerow(["# bmi", f"{bmi:.2f}"])
        writer.writerow(["# hypertension", demographics["preop_htn"]])
        writer.writerow(["# diabetes", demographics["preop_dm"]])
        
        # Glucose data
        writer.writerow(["# predicted_glucose_mmol_L", f"{prediction / 18.0182:.2f}" if prediction is not None else "N/A"])
        writer.writerow(["# predicted_glucose_mg_dL", f"{prediction:.1f}" if prediction is not None else "N/A"])
        writer.writerow(["# calibrated_glucose_mmol_L", f"{calibrated_glucose / 18.0182:.2f}" if calibrated_glucose is not None else "N/A"])
        writer.writerow(["# calibrated_glucose_mg_dL", f"{calibrated_glucose:.1f}" if calibrated_glucose is not None else "N/A"])
        writer.writerow(["# actual_glucose_mmol_L", f"{actual_glucose:.2f}" if actual_glucose is not None else "N/A"])
        writer.writerow(["# actual_glucose_mg_dL", f"{actual_glucose * 18.0182:.1f}" if actual_glucose is not None else "N/A"])
        
        # Metadata
        writer.writerow(["# remarks", remarks.replace("\n", " | ") if remarks.strip() else "N/A"]) 
        writer.writerow(["# n_ppg_samples", len(raw_signal)])
        writer.writerow([])
        writer.writerow(["timestamp_s", "ppg_raw"])
        for t, v in zip(timestamps, raw_signal):
            writer.writerow([f"{t:.4f}", v])

    return filepath, rec_id