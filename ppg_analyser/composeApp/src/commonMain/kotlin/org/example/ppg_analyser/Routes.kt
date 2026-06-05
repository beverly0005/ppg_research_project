package org.example.ppg_analyser

import kotlinx.serialization.Serializable

@Serializable
sealed interface Screen {
    @Serializable
    data object Camera : Screen

    @Serializable
    data class Results(val videoUri: String) : Screen
}