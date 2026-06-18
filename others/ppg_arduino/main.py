import serial, time, csv, os
import numpy as np
import matplotlib.pyplot as plt

plt.style.use('ggplot')

## initialize serial port at 115200 baud rate
ser = serial.Serial('/dev/tty.usbserial-110', baudrate=115200)

## set filename and delete it if it already exists
datafile_name = 'test_data.csv'
if os.path.isfile(datafile_name):
    os.remove(datafile_name)

all_data = []
data_duration = 20  # seconds
start_time = None
recording = False

def parse_line(line_str):
    """Parse a line like: red=XXXXX, ir=XXXXX"""
    try:
        parts = dict(item.strip().split('=') for item in line_str.split(','))
        return {
            'red':        int(parts['red']),
            'ir':         int(parts['ir']),
        }
    except:
        return None

print("Waiting for valid HR and SpO2 readings...")

while True:
    try:
        curr_line = ser.readline().decode('utf-8', errors='ignore').strip()

        if not curr_line:
            continue
        print(f"Received: {curr_line}")
        ser.write(b'Start\n')
        
        break

    except KeyboardInterrupt:
        print("\nKeyboard Interrupt detected, stopping early...")
        break

while True:
    try:
        curr_line = ser.readline().decode('utf-8', errors='ignore').strip()
        parsed = parse_line(curr_line)

        if parsed is None:
            print(f"Unrecognized line format: {curr_line}")
            continue

        # Build signal quality message
        red_val = parsed['red']
        if red_val < 10000:
            signal_msg = f"red={red_val} | Put less pressure on sensor"
        elif 40000 < red_val < 45000:
            signal_msg = f"red={red_val} | Put more pressure on sensor"
        elif 45000 < red_val < 60000:
            signal_msg = f"red={red_val} | Good signal"
        else:
            signal_msg = f"red={red_val}"
            
        if not recording:
            while 'Good signal' not in signal_msg:
                print(signal_msg, end='\r')
                curr_line = ser.readline().decode('utf-8', errors='ignore').strip()
                parsed = parse_line(curr_line)
                if parsed is not None:
                    red_val = parsed['red']
                    if red_val < 10000:
                        signal_msg = f"red={red_val} | Put less pressure on sensor"
                    elif 40000 < red_val < 45000:
                        signal_msg = f"red={red_val} | Put more pressure on sensor"
                    elif 45000 < red_val < 60000:
                        signal_msg = f"red={red_val} | Good signal"
                    else:
                        signal_msg = f"red={red_val}"
                        
            recording = True
            start_time = time.time()
            print("Good signal detected. Starting data collection...")
        
        else:
            # Recording phase
            elapsed = time.time() - start_time
            print(f"Elapsed: {elapsed:.2f}s | {signal_msg}", end='\r')

            if elapsed <= data_duration:
                all_data.append({
                    'time':  elapsed,
                    'red':   parsed['red'],
                    'ir':    parsed['ir'],
                })
            else:
                break

    except KeyboardInterrupt:
        print("\nKeyboard Interrupt detected, stopping early...")
        break

print(f"\nExited Loop. Collected {len(all_data)} samples.")

## Save data
if all_data:
    with open(datafile_name, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Time', 'IR', 'RED'])
        for d in all_data:
            writer.writerow([d['time'], d['ir'], d['red']])
    print(f"Data saved to {datafile_name}")

    times = [d['time'] for d in all_data]
    if len(times) > 1:
        print(f"Sample Rate: {1.0 / np.mean(np.abs(np.diff(times))):.1f} Hz")
else:
    print("No data collected.")