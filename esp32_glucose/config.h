#pragma once

// ─────────────────────────────────────────────────────────────────────────────
//  config.h  –  Pin assignments, DSP constants, scaler params
//  Board : Waveshare ESP32-S3-DEV-KIT-N16R8  (16 MB Flash, 8 MB OPI PSRAM)
//  Core  : esp32 Arduino core 2.x  (downgraded from 3.x)
//
//  Pin reference: https://www.circuitstate.com/pinouts/waveshare-esp32-s3-dev-kit-nxr8
//  GPIO 43 = U0TXD (Serial0 TX)   GPIO 44 = U0RXD (Serial0 RX)
//  GPIO 17 = U1TXD (UART1 TX)     GPIO 18 = U1RXD (UART1 RX)
//  GPIO 38 = onboard RGB LED  →  avoid
//  GPIO 26–37 = internal Flash/PSRAM  →  not on header, avoid
// ─────────────────────────────────────────────────────────────────────────────

// ── Oximeter UART (Serial1) ───────────────────────────────────────────────────
// UART1 hardware defaults are GPIO17(TX) / GPIO18(RX).
// These overlap with keypad columns C3/C4 (GPIO17,18) below.
// We reassign UART1 to GPIO43(TX) / GPIO44(RX) — the physical Serial0/USB-UART
// pins — which we can freely use as a second UART since Serial0 is only needed
// during programming/debugging (not at runtime).
// NOTE: if you use Serial.print() for debug output, use the USB-CDC port
// (accessed via the other USB connector or via Serial in Arduino with CDC).
#define OXI_TX_PIN   GPIO_NUM_43   // ESP32-S3 UART TX → oximeter RX   (U0TXD)
#define OXI_RX_PIN   GPIO_NUM_44   // ESP32-S3 UART RX ← oximeter TX   (U0RXD)
#define OXI_BAUD     115200

// ── OLED (I²C, 128 × 64, SSD1306) ────────────────────────────────────────────
// GPIO8 = SDA, GPIO9 = SCL — general purpose, no conflicts.
// With esp32 core 2.x: Wire.begin(SDA, SCL) must be called explicitly;
// the default Wire pins on S3 are also 8/9 but calling it explicitly is safer.
// Most 0.96" SSD1306 modules use address 0x3C.
// If the display shows gibberish or nothing, see i2c_scanner.ino to confirm.
#define OLED_SDA     GPIO_NUM_8
#define OLED_SCL     GPIO_NUM_9
#define OLED_ADDR    0x3C   // try 0x3D if 0x3C doesn't work
#define OLED_W       128
#define OLED_H       64

// ── 4×4 Matrix Keypad ─────────────────────────────────────────────────────────
// Rows 4–7 and Cols 15–18.
// GPIO15 = U0RTS, GPIO16 = U0CTS — alternate functions, but safe as GPIO.
// GPIO17 = U1TXD, GPIO18 = U1RXD — alternate functions; safe as GPIO since
//   UART1 is remapped to GPIO43/44 above.
// All 8 pins are physically adjacent on the board header — no jumpers needed.
//  Row pins  (OUTPUT — driven by ESP32)
#define KP_R1  GPIO_NUM_4
#define KP_R2  GPIO_NUM_5
#define KP_R3  GPIO_NUM_6
#define KP_R4  GPIO_NUM_7
//  Col pins  (INPUT_PULLUP — read by ESP32)
#define KP_C1  GPIO_NUM_15
#define KP_C2  GPIO_NUM_16
#define KP_C3  GPIO_NUM_17
#define KP_C4  GPIO_NUM_18

// ── Signal / DSP ─────────────────────────────────────────────────────────────
#define OLD_FREQUENCY      40.5f
#define NEW_FREQUENCY      100.0f
#define COLLECT_SECONDS    20

#define MAX_RAW_SAMPLES    1200
#define MAX_RESAMP_SAMPLES 2600

#define BP_LOW    0.5f
#define BP_HIGH   6.0f
#define BP_ORDER  3

#define VALLEY_SEARCH_MIN_S  0.15f
#define VALLEY_SEARCH_MAX_S  0.70f
#define PEAK_MIN_DIST_S      0.05f
#define PEAK_PROM_MAD_MULT   3.0f

#define NUM_SEGMENTS   15
#define SEG_LEN        100
#define SIGNAL_LEN     1500
#define MAX_VALLEYS    200
#define MAX_PEAKS      200

// ── Demographics ──────────────────────────────────────────────────────────────
// Model input: [age, sex, height, weight, bmi, actual_hr, preop_htn, preop_dm]
#define NUM_DEMO_FEAT  8

// ── TFLite tensor arena ───────────────────────────────────────────────────────
#define TENSOR_ARENA_SIZE  (2 * 1024 * 1024)   // 2 MB in OPI PSRAM

// ── StandardScaler — extracted from scaler.pkl ────────────────────────────────
// Features (order): age, weight, bmi, height, actual_hr
// Binary features (sex, preop_htn, preop_dm) are NOT scaled.
#define NUM_SCALED_FEAT  5
static const float SCALER_MEAN[NUM_SCALED_FEAT] = {
     55.20598752f,   // age
     64.63251729f,   // weight   (kg)
     23.50403947f,   // bmi
    165.37427053f,   // height   (cm)
     80.61671435f,   // actual_hr (bpm)
};
static const float SCALER_STD[NUM_SCALED_FEAT] = {
     16.31637246f,   // age
     12.31756268f,   // weight
      3.58627559f,   // bmi
     10.51182365f,   // height
     15.85493746f,   // actual_hr
};
