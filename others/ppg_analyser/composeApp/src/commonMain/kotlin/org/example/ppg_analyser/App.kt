package org.example.ppg_analyser

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute

@Composable
@Preview
fun App() {
    MaterialTheme {
        val navController = rememberNavController()

        NavHost(
            navController = navController,
            startDestination = Screen.Camera
        ) {
            composable<Screen.Camera> {
                CameraScreen(onResultAvailable = {
                    videoUri -> navController.navigate(Screen.Results(videoUri))
                })
            }

            composable<Screen.Results> {
                backStackEntry -> val results: Screen.Results = backStackEntry.toRoute()
                ResultsScreen(results.videoUri)
            }
        }
    }
}