# ─────────────────────────────────────────────────────────────────────────────
#  CMakeLists.txt  –  Top-level project file
#  ESP-IDF build system (idf.py)
# ─────────────────────────────────────────────────────────────────────────────
cmake_minimum_required(VERSION 3.22)

# Pull in ESP-IDF CMake infrastructure
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(esp32_glucose)
