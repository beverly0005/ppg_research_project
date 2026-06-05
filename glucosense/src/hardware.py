import serial
import serial.tools.list_ports
import threading
import time

def get_serial_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    ports.sort(key=lambda p: 0 if "usbserial" in p.lower() else 1)
    return ports if ports else ["/dev/tty.usbserial-110", "/dev/tty.usbserial-10"]

def continuous_serial_reader(port, baud, duration_box, min_duration_box, sig_queue, record_evt, shutdown_evt):
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1.0) 
        time.sleep(1) 
    except Exception as e:
        sig_queue.put(("error", f"Could not connect to {port}: {e}"))
        return

    is_currently_recording = False
    start_time = 0

    while not shutdown_evt.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            print(line)
            
            if record_evt.is_set():
                if not is_currently_recording:
                    is_currently_recording = True
                    start_time = time.time()
                    sig_queue.put(("started", None))

                if not line:
                    continue

                elapsed = time.time() - start_time
                sig_queue.put(("time", elapsed))
                
                if elapsed > duration_box[0]:
                    record_evt.clear()
                    is_currently_recording = False
                    sig_queue.put(("done", None))
                    continue
                
                if line.startswith("AT+MD:0") or line.startswith("U1:0"):
                    if is_currently_recording and elapsed >= min_duration_box[0]:
                        # Hardware reset, but we passed the minimum duration! Wrap it up successfully.
                        record_evt.clear()
                        is_currently_recording = False
                        sig_queue.put(("done", None))
                    else:
                        # Hardware reset BEFORE min duration. Wipe and restart.
                        start_time = time.time()
                        sig_queue.put(("reset", None))
                    continue

                if line.startswith("AT+MD:0") or line.startswith("U1:0"):
                    start_time = time.time()
                    sig_queue.put(("reset", None))
                    continue
                elif line.startswith("U1:"):
                    try:
                        val = int(line.split(":")[1])
                        sig_queue.put(("u1", (elapsed, val)))
                    except Exception: pass
                elif line.startswith("U2:"):
                    try:
                        vals = line.split(":")[1].split(",")
                        sig_queue.put(("u2", (elapsed, int(vals[0]), int(vals[1]), float(vals[2]))))
                    except Exception: pass
            else:
                if is_currently_recording:
                    is_currently_recording = False
                    sig_queue.put(("done", None))

        except Exception:
            pass

    try:
        ser.close()
    except Exception:
        pass