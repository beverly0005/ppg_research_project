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

// Forward declaration of sender function so init can use it
static void oxi_send(const char* cmd);

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

    // 👉 Requirement 1: Send the start command immediately upon initializing peripherals
    vTaskDelay(pdMS_TO_TICKS(100)); // Short stabilization wait
    ESP_LOGI(TAG, "Initializing Oximeter Stream Command...");
    oxi_send("AT+MD:0\r\n");
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

// Global baseline tracking variable to display on the screen live
static long  current_live_value = 0;
// Global variable to request a pipeline reset from inside line processing
static bool  reset_requested = false; 

// ─────────────────────────────────────────────────────────────────────────────
//  Parse oximeter line:  "U1:12345\r\n"
// ─────────────────────────────────────────────────────────────────────────────
static void handle_oxi_line(const char* line, float elapsed_s, float min_duration_s) {
    if (strncmp(line, "U1:", 3) != 0) return;
    const char* v = line + 3;
    long val = atol(v);
    
    // 👉 Requirement 2: Detect hardware drop packet "U1:0"
    if (val == 0 && strlen(v) <= 2) {  
        if (elapsed_s >= min_duration_s) {
            // We passed minimum duration, ignore the error drop and let the loop complete!
            ESP_LOGW(TAG, "U1:0 reset ignored. Passed min duration limit (%.1fs)", min_duration_s);
        } else {
            // Threshold unmet; flag a complete data stream wipe
            ESP_LOGW(TAG, "U1:0 reset triggered! Elapsed: %.1fs < Threshold: %.1fs. Re-starting...", elapsed_s, min_duration_s);
            reset_requested = true;
        }
        return; 
    }
    
    if (raw_count < MAX_RAW_SAMPLES) {
        raw_signal[raw_count] = (float)val;
        raw_times [raw_count] = elapsed_s;
        raw_count++;
        current_live_value = val; // Store value for UI use
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Measurement task: collect COLLECT_SECONDS of PPG
// ─────────────────────────────────────────────────────────────────────────────
static void do_measurement() {
    // Define bounds matching Python logic context
    const float MIN_DURATION_SECS = 16.0f;
    
    // Ensure stream configuration command is updated fresh
    oxi_send("AT+MD:0\r\n");
    vTaskDelay(pdMS_TO_TICKS(100));

    uint8_t  uart_buf[OXI_BUF_SIZE];
    char     line_buf[64];
    int      line_pos    = 0;
    
    // Initialize tracking timestamps
    int64_t  start_us    = esp_timer_get_time();
    int64_t  total_us    = (int64_t)COLLECT_SECONDS * 1000000LL;
    raw_count            = 0;
    reset_requested      = false;
    current_live_value   = 0;

    while (true) {
        int64_t elapsed_us = esp_timer_get_time() - start_us;
        
        if (reset_requested) {
            ESP_LOGI(TAG, "Wiping internal data buffers for fresh collection...");
            raw_count          = 0;
            current_live_value = 0;
            reset_requested    = false;
            line_pos           = 0;
            start_us           = esp_timer_get_time(); // Reset internal execution clock ticker back to zero
            continue;
        }

        if (elapsed_us >= total_us) break;

        int pct = (int)(elapsed_us * 100 / total_us);
        
        // 👉 Requirement 3: Re-format UI to print progress alongside our runtime integer measurement value
        char progress_msg[48];
        snprintf(progress_msg, sizeof(progress_msg), "PPG Raw: %ld", current_live_value);
        ui_progress(progress_msg, pct);

        int len = uart_read_bytes(OXI_UART, uart_buf,
                                  sizeof(uart_buf) - 1, pdMS_TO_TICKS(20));
        for (int i = 0; i < len; i++) {
            char c = (char)uart_buf[i];
            if (c == '\n' || c == '\r') {
                if (line_pos > 0) {
                    line_buf[line_pos] = '\0';
                    handle_oxi_line(line_buf, (float)elapsed_us / 1e6f, MIN_DURATION_SECS);
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

    // // ── Self-test: run inference on synthetic data ───────────────────────────
    // {
    //     ESP_LOGI(TAG, "[SELFTEST] Running inference on synthetic data ...");
    //     ui_print("Self-test...", "Synthetic input");

    //     static float test_signal[SIGNAL_LEN];
    //     static float test_mask[SIGNAL_LEN];
    //     for (int seg = 0; seg < NUM_SEGMENTS; seg++) {
    //         int real_len = 80;   
    //         for (int i = 0; i < SEG_LEN; i++) {
    //             int idx = seg * SEG_LEN + i;
    //             if (i < real_len) {
    //                 float t = (float)i / real_len;
    //                 test_signal[idx] = 0.5f + 0.5f * sinf(t * 6.283f);
    //                 test_mask[idx]   = 1.0f;
    //             } else {
    //                 test_signal[idx] = 0.0f;
    //                 test_mask[idx]   = 0.0f;
    //             }
    //         }
    //     }

    //     static float test_demo[NUM_DEMO_FEAT] = {
    //         0.0f, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f
    //     };

    //     int64_t t0   = esp_timer_get_time();
    //     float   pred = model_infer(test_signal, test_mask, test_demo);
    //     int64_t t1   = esp_timer_get_time();
    //     float   ms   = (t1 - t0) / 1000.0f;

    //     if (isnan(pred)) {
    //         ESP_LOGE(TAG, "[SELFTEST] FAILED — model_infer returned NaN");
    //         ui_print("Self-test FAILED", "Inference error", "Check model_data.h");
    //         while (true) vTaskDelay(pdMS_TO_TICKS(500));
    //     }

    //     ESP_LOGI(TAG, "[SELFTEST] PASSED");
    //     ESP_LOGI(TAG, "[SELFTEST] Prediction : %.4f mg/dL", pred);
    //     ESP_LOGI(TAG, "[SELFTEST] Infer time : %.1f ms", ms);
    //     ESP_LOGI(TAG, "[SELFTEST] Arena used : %u bytes", (unsigned)590104); 

    //     char line2[32], line3[32], line4[32];
    //     snprintf(line2, sizeof(line2), "Pred: %.4f mg/dL", pred);
    //     snprintf(line3, sizeof(line3), "Time: %.0f ms", ms);
    //     snprintf(line4, sizeof(line4), "Press D to continue");
    //     ui_print("Self-test PASSED", line2, line3, line4);

    //     char k = '\0';
    //     while (k != 'D') { k = keypad_scan(); vTaskDelay(pdMS_TO_TICKS(50)); }
    // }

    // ── Main state machine ────────────────────────────────────────────────────
    enum State { HOME, COLLECT_DEMO, MEASURING, PROCESSING, RESULT, ERR };
    State state = HOME;
    Demographics demo_data = {};

    ui_print("Glucose Monitor", "D=Start  C=Test");

    while (true) {
        switch (state) {

        case HOME: {
            char k = keypad_scan();
            if (k == 'D') {
                state = COLLECT_DEMO;
            } else if (k == 'C') {
                ESP_LOGI(TAG, "=== DEMO MODE ===");
                ui_print("Demo Mode", "Generating", "synthetic PPG...");
                vTaskDelay(pdMS_TO_TICKS(1000));

                const float FS_SYN = 40.5f;
                const int   N_SYN  = (int)(20 * FS_SYN);  
                for (int i = 0; i < N_SYN && i < MAX_RAW_SAMPLES; i++) {
                    float t = i / FS_SYN;
                    raw_signal[i] = 2000.0f
                        + 500.0f * sinf(2 * M_PI * 1.0f * t)
                        + 100.0f * sinf(2 * M_PI * 2.0f * t)
                        +  30.0f * sinf(2 * M_PI * 3.0f * t);
                    raw_times[i]  = t;
                }
                raw_count = N_SYN;

                demo_data = { .age=50, .sex=1, .height_cm=170,
                              .weight_kg=70, .preop_htn=0, .preop_dm=0 };
                state = PROCESSING;
            } else {
                vTaskDelay(pdMS_TO_TICKS(50));
            }
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

            float fs_raw = OLD_FREQUENCY;
            if (raw_count > 2) {
                float sum_dt = 0;
                for (int i = 1; i < raw_count; i++)
                    sum_dt += raw_times[i] - raw_times[i-1];
                float mean_dt = sum_dt / (raw_count - 1);
                if (mean_dt > 0.001f) fs_raw = 1.0f / mean_dt;
            }
            ESP_LOGI(TAG, "fs_raw=%.2f Hz, n_raw=%d", fs_raw, raw_count);

            float* detrended = nullptr;
            int    n_det     = 0;
            bool   ok = preprocess_pipeline(raw_signal, raw_count, fs_raw,
                                            signal_1500, mask_1500,
                                            &detrended, &n_det);

            if (!ok || n_det < 10) {
                char err1[32], err2[32];
                snprintf(err1, sizeof(err1), "n_raw=%d fs=%.1f", raw_count, fs_raw);
                snprintf(err2, sizeof(err2), "n_det=%d ok=%d", n_det, (int)ok);
                ESP_LOGE(TAG, "Preprocessing failed: %s %s", err1, err2);
                ui_print("Preprocess failed", err1, err2, "Press D to retry");
                char k = '\0';
                while (k != 'D') { k = keypad_scan(); vTaskDelay(pdMS_TO_TICKS(50)); }
                state = HOME;
                ui_print("Glucose Monitor", "Press D to start");
                break;
            }
            ESP_LOGI(TAG, "Preprocessing OK: n_det=%d", n_det);

            float actual_hr = sample_heart_rate(detrended, n_det, NEW_FREQUENCY);
            if (isnan(actual_hr)) actual_hr = 80.61f;

            float age    = (float)demo_data.age;
            float sex    = (float)demo_data.sex;
            float height = (float)demo_data.height_cm;
            float weight = (float)demo_data.weight_kg;
            float bmi    = weight / ((height / 100.0f) * (height / 100.0f));
            float htn    = (float)demo_data.preop_htn;
            float dm     = (float)demo_data.preop_dm;

            ESP_LOGI(TAG, "Demographics: age=%.0f sex=%.0f height=%.0f weight=%.0f bmi=%.1f htn=%.0f dm=%.0f hr=%.1f", age, sex, height, weight, bmi, htn, dm, actual_hr);

            scale_demographics(age, weight, bmi, height, actual_hr);

            float demo_vec[NUM_DEMO_FEAT] = {
                age, height, weight, bmi, actual_hr, sex, dm, htn
            };

            ui_print("Running model...", "Please wait");
            int64_t t0   = esp_timer_get_time();
            float   pred = model_infer(signal_1500, mask_1500, demo_vec);
            float   ms   = (esp_timer_get_time() - t0) / 1000.0f;

            if (isnan(pred)) {
                ESP_LOGE(TAG, "model_infer returned NaN");
                state = ERR;
                break;
            }
            
            ESP_LOGI(TAG, "=== START RAW DATA DUMP ===");
            printf("SIGNAL_1500 = [");
            for (int i = 0; i < SIGNAL_LEN; i++) {
                printf("%.6f", signal_1500[i]);
                if (i < SIGNAL_LEN - 1) printf(", ");
            }
            printf("]\n");

            printf("MASK_1500 = [");
            for (int i = 0; i < SIGNAL_LEN; i++) {
                printf("%.1f", mask_1500[i]);
                if (i < SIGNAL_LEN - 1) printf(", ");
            }
            printf("]\n");
            ESP_LOGI(TAG, "=== END RAW DATA DUMP ===");

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