#pragma once
#include "driver/i2c.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "config.h"

// ─────────────────────────────────────────────────────────────────────────────
//  ui.h  –  SH1106G OLED + 4×4 keypad   (ESP-IDF, no Arduino)
//
//  OLED: driven via raw I2C using esp-idf driver/i2c.h
//        SH1106 uses a 132-column internal RAM mapped to 128 visible pixels.
//        Each page write must start at column offset 2 (not 0).
//
//  Keypad: direct GPIO polling (no Arduino Keypad library needed).
// ─────────────────────────────────────────────────────────────────────────────

#include "driver/gpio.h"

static const char* TAG_UI = "UI";

// ─────────────────────────────────────────────────────────────────────────────
//  SH1106 I2C driver (bare-metal, no external library)
// ─────────────────────────────────────────────────────────────────────────────
#define I2C_PORT      I2C_NUM_0
#define I2C_FREQ_HZ   400000
#define SH1106_PAGES  8      // 8 pages × 8 rows = 64 rows
#define SH1106_COLS   128
#define SH1106_COL_OFFSET 2  // SH1106 internal RAM offset

static uint8_t g_framebuf[SH1106_PAGES][SH1106_COLS];  // 1 KB framebuffer

static esp_err_t sh1106_send_cmd(uint8_t cmd) {
    uint8_t buf[2] = {0x00, cmd};  // 0x00 = control byte: Co=0, D/C=0
    i2c_cmd_handle_t h = i2c_cmd_link_create();
    i2c_master_start(h);
    i2c_master_write_byte(h, (OLED_ADDR << 1) | I2C_MASTER_WRITE, true);
    i2c_master_write(h, buf, 2, true);
    i2c_master_stop(h);
    esp_err_t r = i2c_master_cmd_begin(I2C_PORT, h, pdMS_TO_TICKS(100));
    i2c_cmd_link_delete(h);
    return r;
}

static void sh1106_flush() {
    for (int page = 0; page < SH1106_PAGES; page++) {
        // Set page address
        sh1106_send_cmd(0xB0 | page);
        // Set column address (SH1106 offset = 2)
        sh1106_send_cmd(0x00 | ((SH1106_COL_OFFSET) & 0x0F));        // low nibble
        sh1106_send_cmd(0x10 | ((SH1106_COL_OFFSET >> 4) & 0x0F));   // high nibble

        // Send 128 data bytes for this page
        uint8_t data_buf[SH1106_COLS + 1];
        data_buf[0] = 0x40;  // control byte: Co=0, D/C=1 (data)
        memcpy(data_buf + 1, g_framebuf[page], SH1106_COLS);

        i2c_cmd_handle_t h = i2c_cmd_link_create();
        i2c_master_start(h);
        i2c_master_write_byte(h, (OLED_ADDR << 1) | I2C_MASTER_WRITE, true);
        i2c_master_write(h, data_buf, SH1106_COLS + 1, true);
        i2c_master_stop(h);
        i2c_master_cmd_begin(I2C_PORT, h, pdMS_TO_TICKS(100));
        i2c_cmd_link_delete(h);
    }
}

static void sh1106_clear() {
    memset(g_framebuf, 0, sizeof(g_framebuf));
}

// 5×7 ASCII font (printable chars 0x20–0x7E), 1 byte per column, 5 cols wide
// Compact subset — full 96-char 5×7 font
static const uint8_t FONT5x7[][5] = {
    {0x00,0x00,0x00,0x00,0x00}, // ' '
    {0x00,0x00,0x5F,0x00,0x00}, // '!'
    {0x00,0x07,0x00,0x07,0x00}, // '"'
    {0x14,0x7F,0x14,0x7F,0x14}, // '#'
    {0x24,0x2A,0x7F,0x2A,0x12}, // '$'
    {0x23,0x13,0x08,0x64,0x62}, // '%'
    {0x36,0x49,0x55,0x22,0x50}, // '&'
    {0x00,0x05,0x03,0x00,0x00}, // '''
    {0x00,0x1C,0x22,0x41,0x00}, // '('
    {0x00,0x41,0x22,0x1C,0x00}, // ')'
    {0x08,0x2A,0x1C,0x2A,0x08}, // '*'
    {0x08,0x08,0x3E,0x08,0x08}, // '+'
    {0x00,0x50,0x30,0x00,0x00}, // ','
    {0x08,0x08,0x08,0x08,0x08}, // '-'
    {0x00,0x60,0x60,0x00,0x00}, // '.'
    {0x20,0x10,0x08,0x04,0x02}, // '/'
    {0x3E,0x51,0x49,0x45,0x3E}, // '0'
    {0x00,0x42,0x7F,0x40,0x00}, // '1'
    {0x42,0x61,0x51,0x49,0x46}, // '2'
    {0x21,0x41,0x45,0x4B,0x31}, // '3'
    {0x18,0x14,0x12,0x7F,0x10}, // '4'
    {0x27,0x45,0x45,0x45,0x39}, // '5'
    {0x3C,0x4A,0x49,0x49,0x30}, // '6'
    {0x01,0x71,0x09,0x05,0x03}, // '7'
    {0x36,0x49,0x49,0x49,0x36}, // '8'
    {0x06,0x49,0x49,0x29,0x1E}, // '9'
    {0x00,0x36,0x36,0x00,0x00}, // ':'
    {0x00,0x56,0x36,0x00,0x00}, // ';'
    {0x00,0x08,0x14,0x22,0x41}, // '<'
    {0x14,0x14,0x14,0x14,0x14}, // '='
    {0x41,0x22,0x14,0x08,0x00}, // '>'
    {0x02,0x01,0x51,0x09,0x06}, // '?'
    {0x32,0x49,0x79,0x41,0x3E}, // '@'
    {0x7E,0x11,0x11,0x11,0x7E}, // 'A'
    {0x7F,0x49,0x49,0x49,0x36}, // 'B'
    {0x3E,0x41,0x41,0x41,0x22}, // 'C'
    {0x7F,0x41,0x41,0x22,0x1C}, // 'D'
    {0x7F,0x49,0x49,0x49,0x41}, // 'E'
    {0x7F,0x09,0x09,0x09,0x01}, // 'F'
    {0x3E,0x41,0x49,0x49,0x7A}, // 'G'
    {0x7F,0x08,0x08,0x08,0x7F}, // 'H'
    {0x00,0x41,0x7F,0x41,0x00}, // 'I'
    {0x20,0x40,0x41,0x3F,0x01}, // 'J'
    {0x7F,0x08,0x14,0x22,0x41}, // 'K'
    {0x7F,0x40,0x40,0x40,0x40}, // 'L'
    {0x7F,0x02,0x04,0x02,0x7F}, // 'M'
    {0x7F,0x04,0x08,0x10,0x7F}, // 'N'
    {0x3E,0x41,0x41,0x41,0x3E}, // 'O'
    {0x7F,0x09,0x09,0x09,0x06}, // 'P'
    {0x3E,0x41,0x51,0x21,0x5E}, // 'Q'
    {0x7F,0x09,0x19,0x29,0x46}, // 'R'
    {0x46,0x49,0x49,0x49,0x31}, // 'S'
    {0x01,0x01,0x7F,0x01,0x01}, // 'T'
    {0x3F,0x40,0x40,0x40,0x3F}, // 'U'
    {0x1F,0x20,0x40,0x20,0x1F}, // 'V'
    {0x3F,0x40,0x38,0x40,0x3F}, // 'W'
    {0x63,0x14,0x08,0x14,0x63}, // 'X'
    {0x07,0x08,0x70,0x08,0x07}, // 'Y'
    {0x61,0x51,0x49,0x45,0x43}, // 'Z'
    {0x00,0x7F,0x41,0x41,0x00}, // '['
    {0x02,0x04,0x08,0x10,0x20}, // '\'
    {0x00,0x41,0x41,0x7F,0x00}, // ']'
    {0x04,0x02,0x01,0x02,0x04}, // '^'
    {0x40,0x40,0x40,0x40,0x40}, // '_'
    {0x00,0x01,0x02,0x04,0x00}, // '`'
    {0x20,0x54,0x54,0x54,0x78}, // 'a'
    {0x7F,0x48,0x44,0x44,0x38}, // 'b'
    {0x38,0x44,0x44,0x44,0x20}, // 'c'
    {0x38,0x44,0x44,0x48,0x7F}, // 'd'
    {0x38,0x54,0x54,0x54,0x18}, // 'e'
    {0x08,0x7E,0x09,0x01,0x02}, // 'f'
    {0x0C,0x52,0x52,0x52,0x3E}, // 'g'
    {0x7F,0x08,0x04,0x04,0x78}, // 'h'
    {0x00,0x44,0x7D,0x40,0x00}, // 'i'
    {0x20,0x40,0x44,0x3D,0x00}, // 'j'
    {0x7F,0x10,0x28,0x44,0x00}, // 'k'
    {0x00,0x41,0x7F,0x40,0x00}, // 'l'
    {0x7C,0x04,0x18,0x04,0x78}, // 'm'
    {0x7C,0x08,0x04,0x04,0x78}, // 'n'
    {0x38,0x44,0x44,0x44,0x38}, // 'o'
    {0x7C,0x14,0x14,0x14,0x08}, // 'p'
    {0x08,0x14,0x14,0x18,0x7C}, // 'q'
    {0x7C,0x08,0x04,0x04,0x08}, // 'r'
    {0x48,0x54,0x54,0x54,0x20}, // 's'
    {0x04,0x3F,0x44,0x40,0x20}, // 't'
    {0x3C,0x40,0x40,0x40,0x7C}, // 'u'
    {0x1C,0x20,0x40,0x20,0x1C}, // 'v'
    {0x3C,0x40,0x30,0x40,0x3C}, // 'w'
    {0x44,0x28,0x10,0x28,0x44}, // 'x'
    {0x0C,0x50,0x50,0x50,0x3C}, // 'y'
    {0x44,0x64,0x54,0x4C,0x44}, // 'z'
    {0x00,0x08,0x36,0x41,0x00}, // '{'
    {0x00,0x00,0x7F,0x00,0x00}, // '|'
    {0x00,0x41,0x36,0x08,0x00}, // '}'
    {0x08,0x04,0x08,0x10,0x08}, // '~'
};

// Draw character at pixel column x, page row (0-7)
static void sh1106_draw_char(int x, int page, char c) {
    if (c < 0x20 || c > 0x7E) c = '?';
    const uint8_t* glyph = FONT5x7[c - 0x20];
    for (int col = 0; col < 5 && (x + col) < SH1106_COLS; col++) {
        g_framebuf[page][x + col] = glyph[col];
    }
}

// Draw string at pixel column x, page (0-7). Returns next x.
static int sh1106_draw_str(int x, int page, const char* s) {
    while (*s && x < SH1106_COLS) {
        sh1106_draw_char(x, page, *s++);
        x += 6;  // 5 pixels + 1 gap
    }
    return x;
}

// Draw horizontal progress bar at page 2, from x=2, width=124
static void sh1106_draw_bar(int pct) {
    int fill = 124 * pct / 100;
    for (int x = 2; x < 126; x++) {
        g_framebuf[2][x] = (x - 2 < fill) ? 0xFF : 0x81;  // full or outline top/bot
    }
    g_framebuf[2][1]   = 0xFF;  // left cap
    g_framebuf[2][126] = 0xFF;  // right cap
}

void ui_init() {
    // ── I2C master init ───────────────────────────────────────────────────────
    i2c_config_t conf = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = OLED_SDA,
        .scl_io_num       = OLED_SCL,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master = { .clk_speed = I2C_FREQ_HZ },
        .clk_flags        = 0,
    };
    ESP_ERROR_CHECK(i2c_param_config(I2C_PORT, &conf));
    ESP_ERROR_CHECK(i2c_driver_install(I2C_PORT, I2C_MODE_MASTER, 0, 0, 0));

    // ── SH1106 init sequence ──────────────────────────────────────────────────
    vTaskDelay(pdMS_TO_TICKS(100));  // power-on delay
    const uint8_t init_seq[] = {
        0xAE,        // display off
        0xD5, 0x80,  // clock divide / osc freq
        0xA8, 0x3F,  // multiplex ratio (63 = 64 rows)
        0xD3, 0x00,  // display offset = 0
        0x40,        // display start line = 0
        0xAD, 0x8B,  // charge pump (internal VCC)
        0xA1,        // segment remap (0xA0=normal, 0xA1=flip H)
        0xC8,        // COM output scan direction (0xC0=normal, 0xC8=flip V)
        0xDA, 0x12,  // COM pins config (alt, no remap)
        0x81, 0xFF,  // contrast = max
        0xD9, 0x1F,  // pre-charge period
        0xDB, 0x40,  // VCOMH deselect level
        0xA4,        // entire display on (follow RAM)
        0xA6,        // normal display (not inverted)
        0xAF,        // display on
    };
    for (size_t i = 0; i < sizeof(init_seq); i++)
        sh1106_send_cmd(init_seq[i]);

    sh1106_clear();
    sh1106_flush();
    ESP_LOGI(TAG_UI, "SH1106G init OK");
}

// ─────────────────────────────────────────────────────────────────────────────
//  High-level display helpers
// ─────────────────────────────────────────────────────────────────────────────
// Print up to 4 lines (one per 2 pages = 16px line height)
void ui_print(const char* l1, const char* l2 = nullptr,
              const char* l3 = nullptr, const char* l4 = nullptr) {
    sh1106_clear();
    const char* lines[] = {l1, l2, l3, l4};
    for (int i = 0; i < 4; i++)
        if (lines[i]) sh1106_draw_str(0, i * 2, lines[i]);
    sh1106_flush();
}

void ui_progress(const char* label, int pct) {
    sh1106_clear();
    sh1106_draw_str(0, 0, label);
    sh1106_draw_bar(pct);
    char buf[8]; snprintf(buf, sizeof(buf), "%d%%", pct);
    sh1106_draw_str(54, 4, buf);
    sh1106_flush();
}

// ─────────────────────────────────────────────────────────────────────────────
//  4×4 Matrix Keypad  (GPIO polling, no library)
// ─────────────────────────────────────────────────────────────────────────────
static const gpio_num_t ROW_PINS[4] = {
    (gpio_num_t)KP_R1, (gpio_num_t)KP_R2,
    (gpio_num_t)KP_R3, (gpio_num_t)KP_R4
};
static const gpio_num_t COL_PINS[4] = {
    (gpio_num_t)KP_C1, (gpio_num_t)KP_C2,
    (gpio_num_t)KP_C3, (gpio_num_t)KP_C4
};
static const char KEYMAP[4][4] = {
    {'1','2','3','A'},
    {'4','5','6','B'},
    {'7','8','9','C'},
    {'*','0','#','D'}
};

void keypad_init() {
    for (int r = 0; r < 4; r++) {
        gpio_config_t cfg = {
            .pin_bit_mask = 1ULL << ROW_PINS[r],
            .mode         = GPIO_MODE_OUTPUT,
            .pull_up_en   = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type    = GPIO_INTR_DISABLE,
        };
        gpio_config(&cfg);
        gpio_set_level(ROW_PINS[r], 1);
    }
    for (int c = 0; c < 4; c++) {
        gpio_config_t cfg = {
            .pin_bit_mask = 1ULL << COL_PINS[c],
            .mode         = GPIO_MODE_INPUT,
            .pull_up_en   = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type    = GPIO_INTR_DISABLE,
        };
        gpio_config(&cfg);
    }
}

// Returns '\0' if no key pressed
char keypad_scan() {
    for (int r = 0; r < 4; r++) {
        // Drive row LOW
        gpio_set_level(ROW_PINS[r], 0);
        vTaskDelay(pdMS_TO_TICKS(1));  // settle
        for (int c = 0; c < 4; c++) {
            if (gpio_get_level(COL_PINS[c]) == 0) {
                gpio_set_level(ROW_PINS[r], 1);
                // Debounce
                vTaskDelay(pdMS_TO_TICKS(20));
                return KEYMAP[r][c];
            }
        }
        gpio_set_level(ROW_PINS[r], 1);
    }
    return '\0';
}

char ui_wait_key() {
    char k = '\0';
    while (k == '\0') {
        k = keypad_scan();
        if (k == '\0') vTaskDelay(pdMS_TO_TICKS(10));
    }
    return k;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Input helpers
// ─────────────────────────────────────────────────────────────────────────────
int ui_input_int(const char* label, const char* hint, int max_digits) {
    char entry[8] = {0};
    int  pos = 0;
    while (true) {
        char disp[22];
        snprintf(disp, sizeof(disp), "> %s_", entry);
        ui_print(label, hint, disp, "A=OK  B=Del");
        char k = ui_wait_key();
        if (k >= '0' && k <= '9' && pos < max_digits) {
            entry[pos++] = k; entry[pos] = '\0';
        } else if (k == 'B' && pos > 0) {
            entry[--pos] = '\0';
        } else if ((k == 'A' || k == '#') && pos > 0) {
            return atoi(entry);
        }
    }
}

int ui_input_binary(const char* label, const char* opt0, const char* opt1) {
    int val = 0;
    while (true) {
        char line3[22];
        snprintf(line3, sizeof(line3), ">> %s", val ? opt1 : opt0);
        ui_print(label, "", line3, "C=Toggle A=OK");
        char k = ui_wait_key();
        if (k == 'C') val ^= 1;
        else if (k == 'A' || k == '#') return val;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Demographics collection
// ─────────────────────────────────────────────────────────────────────────────
struct Demographics {
    int age, sex, height_cm, weight_kg, preop_htn, preop_dm;
};

Demographics ui_collect_demographics() {
    Demographics d;
    ui_print("Patient Info", "Fill in details", "", "Press A to start");
    vTaskDelay(pdMS_TO_TICKS(2000));
    d.age       = ui_input_int("Age (years)",  "e.g. 45",  3);
    d.sex       = ui_input_binary("Sex", "Female (0)", "Male   (1)");
    d.height_cm = ui_input_int("Height (cm)", "e.g. 170", 3);
    d.weight_kg = ui_input_int("Weight (kg)", "e.g. 70",  3);
    d.preop_htn = ui_input_binary("Hypertension?", "No  (0)", "Yes (1)");
    d.preop_dm  = ui_input_binary("Diabetes?",     "No  (0)", "Yes (1)");
    char s1[22], s2[22], s3[22];
    snprintf(s1, sizeof(s1), "Age:%d %s", d.age, d.sex ? "M" : "F");
    snprintf(s2, sizeof(s2), "H:%dcm W:%dkg", d.height_cm, d.weight_kg);
    snprintf(s3, sizeof(s3), "HTN:%d DM:%d",  d.preop_htn, d.preop_dm);
    ui_print("Summary:", s1, s2, s3);
    vTaskDelay(pdMS_TO_TICKS(2500));
    return d;
}

void ui_show_result(float glucose_mmol) {
    char l2[22], l3[22], l4[22];
    snprintf(l2, sizeof(l2), "%.1f mmol/L", glucose_mmol);
    snprintf(l3, sizeof(l3), "(%.0f mg/dL)", glucose_mmol * 18.0f);
    const char* status =
        glucose_mmol < 3.9f   ? "LOW"       :
        glucose_mmol <= 7.8f  ? "NORMAL"    :
        glucose_mmol <= 11.1f ? "HIGH"      : "VERY HIGH";
    snprintf(l4, sizeof(l4), "Status: %s", status);
    ui_print("Blood Glucose:", l2, l3, l4);
}
