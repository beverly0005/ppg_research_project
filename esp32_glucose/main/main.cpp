// ─────────────────────────────────────────────────────────────────────────────
//  main/main.cpp  –  ESP-IDF entry point
//  Replaces the Arduino .ino file entirely.
//  Build with: idf.py build  (then idf.py -p /dev/cu.usbmodem1101 flash monitor)
// ─────────────────────────────────────────────────────────────────────────────
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"

#include "config.h"
#include "preprocessing.h"
#include "ui.h"
#include "model_runner.h"

static const char* TAG = "GLUCOSE";

// ── Oximeter UART ─────────────────────────────────────────────────────────────
#define OXI_UART       UART_NUM_1
#define OXI_BUF_SIZE   512

static void oxi_uart_init() {
    uart_config_t uart_config = {}; // Zero-initialize everything first
    uart_config.baud_rate = 115200;
    uart_config.data_bits = UART_DATA_8_BITS;
    uart_config.parity    = UART_PARITY_DISABLE;
    uart_config.stop_bits = UART_STOP_BITS_1;
    uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    uart_config.source_clk = UART_SCLK_DEFAULT;
    ESP_ERROR_CHECK(uart_param_config(OXI_UART, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(OXI_UART, OXI_TX_PIN, OXI_RX_PIN,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(OXI_UART, OXI_BUF_SIZE * 2, 0, 0, NULL, 0));
}

static void oxi_send(const char* cmd) {
    uart_write_bytes(OXI_UART, cmd, strlen(cmd));
}

// ── Raw signal buffer ─────────────────────────────────────────────────────────
static float raw_signal[MAX_RAW_SAMPLES];
static float raw_times[MAX_RAW_SAMPLES];
static int   raw_count = 0;

// ── Pipeline output ───────────────────────────────────────────────────────────
static float signal_1500[SIGNAL_LEN];
static float mask_1500[SIGNAL_LEN];

// ─────────────────────────────────────────────────────────────────────────────
//  Parse oximeter line:  "U1:12345\r\n"
// ─────────────────────────────────────────────────────────────────────────────
static void handle_oxi_line(const char* line, float elapsed_s) {
    if (strncmp(line, "U1:", 3) != 0) return;
    const char* v = line + 3;
    long val = atol(v);
    if (val == 0 && strlen(v) <= 2) return;  // U1:0 reset packet
    if (raw_count < MAX_RAW_SAMPLES) {
        raw_signal[raw_count] = (float)val;
        raw_times [raw_count] = elapsed_s;
        raw_count++;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Measurement task: collect COLLECT_SECONDS of PPG
// ─────────────────────────────────────────────────────────────────────────────
static void do_measurement() {
    raw_count = 0;
    oxi_send("AT+MD:0\r\n");
    vTaskDelay(pdMS_TO_TICKS(200));

    uint8_t  uart_buf[OXI_BUF_SIZE];
    char     line_buf[64];
    int      line_pos    = 0;
    int64_t  start_us    = esp_timer_get_time();
    int64_t  total_us    = (int64_t)COLLECT_SECONDS * 1000000LL;

    while (true) {
        int64_t elapsed_us = esp_timer_get_time() - start_us;
        if (elapsed_us >= total_us) break;

        int pct = (int)(elapsed_us * 100 / total_us);
        ui_progress("Measuring PPG...", pct);

        int len = uart_read_bytes(OXI_UART, uart_buf,
                                  sizeof(uart_buf) - 1, pdMS_TO_TICKS(20));
        for (int i = 0; i < len; i++) {
            char c = (char)uart_buf[i];
            if (c == '\n' || c == '\r') {
                if (line_pos > 0) {
                    line_buf[line_pos] = '\0';
                    handle_oxi_line(line_buf, elapsed_us / 1e6f);
                    line_pos = 0;
                }
            } else if (line_pos < (int)sizeof(line_buf) - 1) {
                line_buf[line_pos++] = c;
            }
        }
    }
    ESP_LOGI(TAG, "Collected %d raw samples", raw_count);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Main app_main — equivalent of Arduino setup() + loop()
// ─────────────────────────────────────────────────────────────────────────────
extern "C" void app_main() {
    // NVS init (required by some ESP-IDF components)
    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    ESP_LOGI(TAG, "[BOOT] ESP32-S3 Glucose Monitor (ESP-IDF + esp-tflite-micro)");

    // ── Peripherals init ──────────────────────────────────────────────────────
    ui_init();
    keypad_init();
    oxi_uart_init();

    ui_print("Loading model...", "Please wait");

    if (!model_init()) {
        ui_print("Model load FAILED", "Check model_data.h");
        ESP_LOGE(TAG, "model_init failed — halting");
        while (true) vTaskDelay(pdMS_TO_TICKS(500));
    }

    // ── Main state machine ────────────────────────────────────────────────────
    enum State { HOME, COLLECT_DEMO, MEASURING, PROCESSING, RESULT, ERR };
    State state = HOME;
    Demographics demo_data = {};

    ui_print("Glucose Monitor", "Press D to start");

    while (true) {
        switch (state) {

        case HOME: {
            char k = keypad_scan();
            if (k == 'D') state = COLLECT_DEMO;
            else vTaskDelay(pdMS_TO_TICKS(50));
            break;
        }

        case COLLECT_DEMO:
            demo_data = ui_collect_demographics();
            state = MEASURING;
            break;

        case MEASURING:
            do_measurement();
            if (raw_count < 100) {
                ui_print("Too few samples!", "Check oximeter");
                vTaskDelay(pdMS_TO_TICKS(3000));
                state = HOME;
            } else {
                state = PROCESSING;
            }
            break;

        case PROCESSING: {
            ui_print("Processing...", "Please wait");

            // Estimate actual sample rate
            float fs_raw = OLD_FREQUENCY;
            if (raw_count > 2) {
                float sum_dt = 0;
                for (int i = 1; i < raw_count; i++)
                    sum_dt += raw_times[i] - raw_times[i-1];
                float mean_dt = sum_dt / (raw_count - 1);
                if (mean_dt > 0.001f) fs_raw = 1.0f / mean_dt;
            }
            ESP_LOGI(TAG, "fs_raw=%.2f Hz, n=%d", fs_raw, raw_count);

            float* detrended = nullptr;
            int    n_det     = 0;
            bool   ok = preprocess_pipeline(raw_signal, raw_count, fs_raw,
                                            signal_1500, mask_1500,
                                            &detrended, &n_det);
            if (!ok || n_det < 10) {
                ui_print("Processing failed", "Not enough peaks", "Check sensor fit");
                vTaskDelay(pdMS_TO_TICKS(3000));
                state = HOME;
                break;
            }

            float actual_hr = sample_heart_rate(detrended, n_det, NEW_FREQUENCY);
            if (isnan(actual_hr)) actual_hr = 80.61f;  // training mean fallback
            ESP_LOGI(TAG, "HR=%.1f bpm", actual_hr);

            float age    = (float)demo_data.age;
            float sex    = (float)demo_data.sex;
            float height = (float)demo_data.height_cm;
            float weight = (float)demo_data.weight_kg;
            float bmi    = weight / ((height / 100.0f) * (height / 100.0f));
            float htn    = (float)demo_data.preop_htn;
            float dm     = (float)demo_data.preop_dm;

            scale_demographics(age, weight, bmi, height, actual_hr);

            float demo_vec[NUM_DEMO_FEAT] = {
                age, sex, height, weight, bmi, actual_hr, htn, dm
            };

            ui_print("Running model...");
            float pred = model_infer(signal_1500, mask_1500, demo_vec);
            ESP_LOGI(TAG, "Prediction: %.4f mmol/L", pred);

            if (isnan(pred)) { state = ERR; break; }
            ui_show_result(pred);
            state = RESULT;
            break;
        }

        case RESULT: {
            char k = keypad_scan();
            if (k != '\0') {
                state = HOME;
                ui_print("Glucose Monitor", "Press D to start");
            }
            vTaskDelay(pdMS_TO_TICKS(50));
            break;
        }

        case ERR:
            ui_print("Inference error", "Press any key");
            if (keypad_scan() != '\0') {
                state = HOME;
                ui_print("Glucose Monitor", "Press D to start");
            }
            vTaskDelay(pdMS_TO_TICKS(50));
            break;
        }
    }
}
