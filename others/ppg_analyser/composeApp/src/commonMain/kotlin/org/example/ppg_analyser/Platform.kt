package org.example.ppg_analyser

interface Platform {
    val name: String
}

expect fun getPlatform(): Platform