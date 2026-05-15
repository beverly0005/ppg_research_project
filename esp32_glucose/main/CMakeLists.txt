# ─────────────────────────────────────────────────────────────────────────────
#  main/CMakeLists.txt
# ─────────────────────────────────────────────────────────────────────────────
idf_component_register(
    SRCS
        "main.cpp"
    INCLUDE_DIRS
        "."
        ".."          # exposes config.h, preprocessing.h, ui.h, model_runner.h
    REQUIRES
        driver        # Legacy driver wrapper
        esp_driver_uart  # <-- Added for UART
        esp_driver_i2c   # <-- Added for I2C
        esp_driver_gpio  # <-- Added for GPIO
        esp_timer
        freertos
        nvs_flash
        esp_psram
        esp-tflite-micro
)

# Use all available flash (16 MB) — adjust if your board differs
target_compile_options(${COMPONENT_LIB} PRIVATE
    -O2
    -DESP_NN              # enable ESP-NN SIMD optimisations
)
