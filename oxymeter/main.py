import serial, time, csv, os
import numpy as np

# serial port
ser = serial.Serial('/dev/tty.usbserial-110', baudrate=115200, timeout=1)

time.sleep(1)
# ser.write(b"AT+MD:0\r\n")

# output files
u1_file = "waveform_u1.csv"
u2_file = "vitals_u2.csv"

for f in [u1_file, u2_file]:
    if os.path.isfile(f):
        os.remove(f)

u1_data = []
u2_data = []

duration = 20
start_time = time.time()

def parse_u1(line):
    try:
        val = int(line.split(":")[1])
        return val
    except:
        return None

def parse_u2(line):
    try:
        vals = line.split(":")[1].split(",")
        return {
            "spo2": int(vals[0]),
            "hr": int(vals[1]),
            "pi": float(vals[2])
        }
    except:
        return None


print("Collecting data...")

while True:
    try:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        
        elapsed = time.time() - start_time
        if elapsed > duration:
            break

        print(line)
        
        if line.startswith("AT+MD:0"):
            start_time = time.time()
            u1_data = []
            u2_data = []
            continue
            
        elif line.startswith("U1:0"):
            start_time = time.time()
            ul_data = []
            u2_data = []
            continue

        elif line.startswith("U1:"):
            val = parse_u1(line)
            if val is not None:
                u1_data.append([elapsed, val])

        elif line.startswith("U2:"):
            parsed = parse_u2(line)
            if parsed is not None:
                u2_data.append([
                    elapsed,
                    parsed["spo2"],
                    parsed["hr"],
                    parsed["pi"]
                ])
        
        print(f"Elapsed: {elapsed:.1f}s", end="\r")

    except KeyboardInterrupt:
        print("Stopped early")
        break


print(f"Collected {len(u1_data)} waveform samples")
print(f"Collected {len(u2_data)} vitals samples")


# save U1 waveform
with open(u1_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["time", "signal"])
    writer.writerows(u1_data)

# save U2 vitals
with open(u2_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["time", "spo2", "heartrate", "perfusion_index"])
    writer.writerows(u2_data)

print("Saved CSV files")


# optional: estimate sampling rate
if len(u1_data) > 2:
    times = [d[0] for d in u1_data]
    sr = 1.0 / np.mean(np.diff(times))
    print(f"Waveform sample rate ≈ {sr:.1f} Hz")