package org.example.ppg_analyser

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import kotlinx.coroutines.*
import platform.Foundation.NSDocumentDirectory
import platform.Foundation.NSFileManager
import platform.Foundation.NSString
import platform.Foundation.NSURL
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.NSUserDomainMask
import platform.Foundation.dataUsingEncoding
import platform.Foundation.writeToURL

@Composable
actual fun ResultsScreen(videoUri: String) {
    // In CMP, we don't need Context for iOS, but we keep the parameter for consistency
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(ProcessingState()) }

    // Start processing when screen loads
    LaunchedEffect(videoUri) {
        // iOS doesn't require runtime permissions to read a file from a provided URL
        // if it came from the picker or the app's own directory.
        scope.launch {
            processVideo("iOS_Context", videoUri) { update ->
                state = update
            }
        }
    }

    MaterialTheme {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            when {
                state.isProcessing -> {
                    ProcessingView(state)
                }
                state.error != null -> {
                    ErrorView(state.error!!)
                }
                state.ppgSignals != null -> {
                    ResultsView(state.ppgSignals!!)
                }
                else -> {
                    Text("Initializing...")
                }
            }
        }
    }
}

actual suspend fun processVideo(
    context: Any, // Unused on iOS but required by actual signature
    videoUri: String,
    onUpdate: (ProcessingState) -> Unit
) {
    withContext(Dispatchers.Default) {
        try {
            onUpdate(ProcessingState(isProcessing = true))

            val extractor = VideoFrameExtractor(context)
            val frames = extractor.extractFrames(videoUri)

            if (frames.isEmpty()) {
                onUpdate(ProcessingState(error = "No frames extracted from video"))
                return@withContext
            }

//             1. Generate CSV Content
            val csvContent = buildString {
                appendLine("index,avgRed,avgGreen,avgBlue,sdRed,avgLum")
                frames.forEachIndexed { index, frame ->
                    appendLine("$index,${frame.avgRed},${frame.avgGreen},${frame.avgBlue},${frame.sdRed},${frame.avgLum}")
                }
            }

            // 2. Save to iOS Documents Directory
            val fileManager = NSFileManager.defaultManager
            val urls = fileManager.URLsForDirectory(NSDocumentDirectory, NSUserDomainMask)
            val documentsDirectory = urls.first() as? NSURL

            if (documentsDirectory != null) {
                val fileURL = documentsDirectory.URLByAppendingPathComponent("ppgsignals_ios.csv")

                val data = (csvContent as NSString).dataUsingEncoding(NSUTF8StringEncoding)
                if (data != null && fileURL != null) {
                    data.writeToURL(fileURL, true)
                    println("CSV saved to: ${fileURL.path}")
                }
            }

            // 3. Final UI Update
            onUpdate(
                ProcessingState(
                    isProcessing = false,
                    ppgSignals = frames
                )
            )

        } catch (e: Exception) {
            onUpdate(
                ProcessingState(
                    isProcessing = false,
                    error = e.message ?: "Unknown iOS Error"
                )
            )
        }
    }
}
