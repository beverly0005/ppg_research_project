# GlucoSense

> **Non-invasive blood glucose estimation via PPG signal analysis.**
> GlucoSense is a real-time, Streamlit-based application that reads live Photoplethysmography (PPG) data from a serial sensor, processes the morphology of the waveforms, and uses a multi-modal PyTorch deep learning model to estimate blood glucose levels.

---

## 🚀 How to Run the Program

To run GlucoSense, you will need Python installed along with several key dependencies for machine learning, signal processing, and data visualization.

### 1. Install Dependencies

Make sure you have the required packages installed. You can typically do this via `pip`:

```bash
pip install -r requirements.txt

```

_(Note: It is highly recommended to use a virtual environment like `venv` or `conda`.)_

### 2. Launch the Application

Navigate to the root directory of the project in your terminal and run the following Streamlit command:

```bash
streamlit run app.py

```

This will start the local web server and open the GlucoSense UI in your default web browser.

---

## 📂 Project Structure & Logic

The project is modularized to separate the front-end user interface from the heavy-lifting of hardware communication and mathematical processing.

### 🎨 User Interface (UI) Management

These files directly control what the user sees and interacts with on the screen:

- **`app.py`**: The main entry point. It manages the Streamlit layout, handles the sidebar form for patient demographics, renders the live oscilloscope view, and displays the final glucose predictions and interactive data charts.
- **`config.py`**: Holds the global session state defaults and the custom CSS string (`APP_CSS`) that dictates the styling, fonts, and colors of the web app.

### 🧠 Core Logic & Signal Processing

These files process the incoming data and manage the predictive modeling:

- **`processing.py`**: The central pipeline controller. It takes the raw signal, orchestrates the resampling (converting to 100 Hz), applies filtering, extracts individual heartbeat segments, standardizes the biometric data, and runs the deep learning model to get a glucose prediction.
- **`filtering_spline.py`**: The mathematical engine for signal cleaning. It applies a Butterworth bandpass filter (to remove drift and high-frequency noise), detects systolic peaks and valleys, and uses Cubic Spline interpolation to remove the baseline wandering from the PPG signal.
- **`multimodal_model.py`**: Defines the PyTorch neural network architecture. It consists of a 1D Convolutional Neural Network (CNN) to extract features from the PPG segments and a Multi-Layer Perceptron (MLP) to process patient demographics (age, BMI, etc.), fusing them to output a continuous glucose value.
- **`storage.py`**: Manages all file I/O operations. It saves full recording sessions as `.csv` files inside a `/recordings` directory and handles reading/writing patient calibration offsets to `calibrations.csv`.

### 🔌 Hardware & Sensor Communication

- **`hardware.py`**: Manages the physical connection to the external sensor device using the `pyserial` library.

---

## 📡 Important Information: How the PPG Sensor Runs

The hardware integration in GlucoSense is designed to capture high-frequency time-series data without freezing the user interface. Here is how the sensor runtime operates:

- **Background Threading:** Reading from a serial port is a blocking operation. To prevent the Streamlit web app from locking up, `hardware.py` spawns a daemon thread (`continuous_serial_reader`). This thread continuously listens to the selected COM port in the background.
- **Thread-Safe Queues:** As the background thread reads raw signals from the sensor, it packages them into tuples (e.g., `("u1", (elapsed_time, value))`) and pushes them into a Python `queue.Queue`. The Streamlit front-end continuously polls this queue during the "Recording" state to update the live UI monitor smoothly.
- **Data Formats:** The program expects the sensor to stream serial data in specific string formats over the chosen Baud Rate (typically 115200):
- `U1: <value>` represents the primary raw PPG waveform data.
- `U2: <val1>,<val2>,<val3>` represents secondary vitals.

- **Hardware Resets & Validation:** The script watches for reset triggers from the hardware (like lines starting with `AT+MD:0` or `U1:0`). If the sensor resets _before_ the user-defined `min_duration` is reached, the app silently wipes the data and restarts the timer. If it resets _after_ the minimum duration, it considers the recording a success and proceeds to processing.
- **Signal Inversion:** It is important to note that the raw signal is inverted during the preprocessing stage (`signal = -raw_signal` inside `processing.py`) before applying the peak-finding algorithms.
