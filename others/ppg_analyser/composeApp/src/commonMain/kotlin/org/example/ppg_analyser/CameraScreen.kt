package org.example.ppg_analyser

import androidx.compose.runtime.Composable

@Composable
expect fun CameraScreen(onResultAvailable: (String) -> Unit)