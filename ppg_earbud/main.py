import asyncio
import csv
import datetime as dt
import os
import sys
import time
from contextlib import suppress
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError


# --- Configuration ---
TARGET_BLE_NAME = "PF2315-177R-0177"  # or a MAC/address/UUID if your OS exposes one

SERVICE_UUID = "40af0001-9479-43f6-ae95-c45fb2afb9d2"
WRITE_CHAR_UUID = "40af0002-9479-43f6-ae95-c45fb2afb9d2"
READ_CHAR_UUID = "40af0003-9479-43f6-ae95-c45fb2afb9d2"

CMD_BATTERY = b"GET_BATL\n"
CMD_STREAM_RAW = b"hrraw 1\n"

CSV_PATH = Path("pf2315_readings.csv")

SCAN_TIMEOUT_SECONDS = 12.0
RECONNECT_DELAY_SECONDS = 3.0
KEEPALIVE_SECONDS = 20.0
FLUSH_EVERY_ROWS = 75

# One row is:
# R + 18 columns from the manual
EXPECTED_PARTS = 19


CSV_FIELDS = [
    "host_time_iso",
    "host_time_unix_ns",
    "sample_index",
    "record_type",

    "ir1",
    "ir2",
    "ir3",
    "ir4",

    "ir1_repeat",
    "ir2_repeat",
    "ir3_repeat",
    "ir4_repeat",

    "red1",
    "red2",
    "red3",
    "red4",

    "accel_x_raw",
    "accel_y_raw",
    "accel_z_raw",

    "accel_x_g",
    "accel_y_g",
    "accel_z_g",

    "reserved",
    "heart_rate",
    "debug",
]


class PF2315LineAssembler:
    """
    Turns arbitrary BLE byte chunks into complete text rows.

    BLE notifications are not row-aligned. For example, the device may send:
        b"R,9"
    then later:
        b"086,8971,...\\n"

    This class buffers those pieces until a full newline-terminated row exists.
    """

    def __init__(self):
        self.buffer = ""

    def feed(self, chunk: str):
        self.buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
        complete_lines = []

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip()

            if not line:
                continue

            # If a newline/chunk boundary appears inside a row, glue it to the next part.
            # Example: "R,9" + "086,..." should become "R,9086,...".
            if line.startswith("R,") and len(line.split(",")) < EXPECTED_PARTS:
                rest = self.buffer.lstrip("\n")
                self.buffer = line + rest

                if "\n" not in self.buffer:
                    break

                continue

            complete_lines.append(line)

        # Avoid unbounded growth if the stream starts mid-record or gets corrupted.
        if len(self.buffer) > 8192:
            last_start = self.buffer.rfind("R,")
            self.buffer = self.buffer[last_start:] if last_start >= 0 else ""

        return complete_lines


def parse_pf2315_line(line: str, sample_index: int):
    """
    Parse one complete PF2315 raw row.

    Expected format:
    R,
    IR1,IR2,IR3,IR4,
    IR1_repeat,IR2_repeat,IR3_repeat,IR4_repeat,
    RED1,RED2,RED3,RED4,
    accel_x,accel_y,accel_z,
    reserved,
    heart_rate,
    debug
    """

    parts = [p.strip() for p in line.split(",")]

    if len(parts) != EXPECTED_PARTS or parts[0] != "R":
        return None

    try:
        ir = [int(x) for x in parts[1:5]]
        ir_repeat = [int(x) for x in parts[5:9]]
        red = [int(x) for x in parts[9:13]]
        accel = [int(x) for x in parts[13:16]]
        reserved = int(parts[16])
        heart_rate = int(parts[17])

        # Keep debug as text because values can be hex-like, e.g. "a9700".
        debug = parts[18]

    except ValueError:
        return None

    now = dt.datetime.now(dt.timezone.utc)

    return {
        "host_time_iso": now.isoformat(timespec="milliseconds"),
        "host_time_unix_ns": time.time_ns(),
        "sample_index": sample_index,
        "record_type": "R",

        "ir1": ir[0],
        "ir2": ir[1],
        "ir3": ir[2],
        "ir4": ir[3],

        "ir1_repeat": ir_repeat[0],
        "ir2_repeat": ir_repeat[1],
        "ir3_repeat": ir_repeat[2],
        "ir4_repeat": ir_repeat[3],

        "red1": red[0],
        "red2": red[1],
        "red3": red[2],
        "red4": red[3],

        "accel_x_raw": accel[0],
        "accel_y_raw": accel[1],
        "accel_z_raw": accel[2],

        # Manual says 255 = 1G.
        "accel_x_g": round(accel[0] / 255.0, 6),
        "accel_y_g": round(accel[1] / 255.0, 6),
        "accel_z_g": round(accel[2] / 255.0, 6),

        "reserved": reserved,
        "heart_rate": heart_rate,
        "debug": debug,
    }


class CsvRecorder:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

        is_new = not self.path.exists() or self.path.stat().st_size == 0

        self.file = self.path.open("a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=CSV_FIELDS)

        if is_new:
            self.writer.writeheader()
            self.file.flush()

        self.rows_written = 0

    def write(self, row: dict):
        self.writer.writerow(row)
        self.rows_written += 1

        if self.rows_written % FLUSH_EVERY_ROWS == 0:
            self.file.flush()
            print(
                f"Saved {self.rows_written} rows "
                f"(last HR={row['heart_rate']}, "
                f"accel_g=({row['accel_x_g']},{row['accel_y_g']},{row['accel_z_g']}))"
            )

    def close(self):
        self.file.flush()
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


async def find_target_device():
    print(f"Scanning for {TARGET_BLE_NAME!r}...")

    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT_SECONDS)

    for device in devices:
        name = device.name or ""
        address = device.address or ""

        if name == TARGET_BLE_NAME or address.lower() == TARGET_BLE_NAME.lower():
            print(f"Found: {name} ({address})")
            return device

    pf_devices = [
        f"{d.name} ({d.address})"
        for d in devices
        if (d.name or "").startswith("PF2315")
    ]

    if pf_devices:
        print("Nearby PF2315 devices:")
        for item in pf_devices:
            print(f"  {item}")
    else:
        print("No PF2315 devices found in this scan.")

    return None


async def write_command(client: BleakClient, command: bytes, label: str):
    """
    Send a command to the PF2315 write characteristic.

    Uses the characteristic properties to choose write-with-response or
    write-without-response. If the device advertises the properties incorrectly,
    it retries once without response.
    """

    response = True

    with suppress(Exception):
        char = client.services.get_characteristic(WRITE_CHAR_UUID)

        if char is not None:
            if "write" in char.properties:
                response = True
            elif "write-without-response" in char.properties:
                response = False

    try:
        await client.write_gatt_char(
            WRITE_CHAR_UUID,
            command,
            response=response,
        )
    except Exception:
        if response:
            await client.write_gatt_char(
                WRITE_CHAR_UUID,
                command,
                response=False,
            )
        else:
            raise

    print(f"Sent {label!r}")


async def keepalive_loop(client: BleakClient, disconnected_event: asyncio.Event):
    """
    Periodically send GET_BATL.

    The manual uses GET_BATL before streaming to avoid the earbud turning off.
    Sending it periodically is a practical keepalive while logging.
    """

    while client.is_connected and not disconnected_event.is_set():
        try:
            await asyncio.wait_for(
                disconnected_event.wait(),
                timeout=KEEPALIVE_SECONDS,
            )
        except asyncio.TimeoutError:
            pass

        if disconnected_event.is_set() or not client.is_connected:
            return

        try:
            await write_command(client, CMD_BATTERY, "GET_BATL keepalive")
        except Exception as exc:
            print(
                f"Keepalive failed; treating as disconnected: {exc!r}",
                file=sys.stderr,
            )
            disconnected_event.set()
            return


async def run_session(device, recorder: CsvRecorder):
    loop = asyncio.get_running_loop()
    disconnected_event = asyncio.Event()
    assembler = PF2315LineAssembler()

    keepalive_task = None
    malformed_rows = 0

    def on_disconnect(_client):
        loop.call_soon_threadsafe(disconnected_event.set)

    def notification_handler(sender, data: bytearray):
        nonlocal malformed_rows

        text = data.decode("ascii", errors="ignore")

        for line in assembler.feed(text):
            # Ignore battery replies or other non-raw lines.
            if not line.startswith("R,"):
                continue

            row = parse_pf2315_line(line, recorder.rows_written + 1)

            if row is None:
                malformed_rows += 1

                if malformed_rows <= 5 or malformed_rows % 100 == 0:
                    print(
                        f"Skipped malformed R row: {line[:160]!r}",
                        file=sys.stderr,
                    )

                continue

            recorder.write(row)

    async with BleakClient(
        device,
        disconnected_callback=on_disconnect,
        services=[SERVICE_UUID],
        timeout=20.0,
    ) as client:
        print(f"Connected to {device.name} ({device.address})")

        await client.start_notify(READ_CHAR_UUID, notification_handler)
        print("Notifications started.")

        await write_command(client, CMD_BATTERY, "GET_BATL")
        await asyncio.sleep(0.5)

        await write_command(client, CMD_STREAM_RAW, "hrraw 1")

        print(f"Logging CSV rows to: {CSV_PATH.resolve()}")

        try:
            await disconnected_event.wait()
            print("BLE disconnected.")
        finally:
            if client.is_connected:
                with suppress(Exception):
                    await client.stop_notify(READ_CHAR_UUID)


async def main():
    print("PF2315 raw logger starting.")
    print("Press Ctrl+C to stop. CSV is appended, not overwritten.")

    with CsvRecorder(CSV_PATH) as recorder:
        while True:
            device = await find_target_device()

            if device is None:
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
                continue

            try:
                await run_session(device, recorder)

            except asyncio.CancelledError:
                raise

            except (BleakError, OSError, TimeoutError) as exc:
                print(f"BLE session error: {exc!r}", file=sys.stderr)

            except Exception as exc:
                print(f"Unexpected session error: {exc!r}", file=sys.stderr)

            print(f"Reconnecting after {RECONNECT_DELAY_SECONDS:.1f}s...")
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")