package org.example.ppg_analyser

import android.Manifest
import android.app.Activity
import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.ActivityCompat
import kotlinx.coroutines.launch

@Composable
actual fun ResultsScreen(videoUri: String) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(ProcessingState()) }

    val permissions = if(Build.VERSION.SDK_INT >= 33) {
        arrayOf(
            Manifest.permission.READ_MEDIA_AUDIO,
            Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_MEDIA_IMAGES
        )
    } else {
        arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
    }

    ActivityCompat.requestPermissions(context as Activity, permissions, 0)

    // Start processing when screen loads
    LaunchedEffect(videoUri) {
        scope.launch {
            processVideo(context, videoUri) { update ->
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
    context: Any,
    videoUri: String,
    onUpdate: (ProcessingState) -> Unit
) {

    try {
        onUpdate(ProcessingState(isProcessing = true))

        val extractor = VideoFrameExtractor(context)
        val frames = extractor.extractFrames(videoUri)

        if (frames.isEmpty()) {
            onUpdate(ProcessingState(error = "No frames extracted from video"))
            return
        }
        val appContext = context as Activity
        val resolver = appContext.contentResolver

        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, "ppgsignals_android.csv")
            put(MediaStore.MediaColumns.MIME_TYPE, "text/csv")
            put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOCUMENTS
            )
        }

        val uri = resolver.insert(
            MediaStore.Files.getContentUri("external"),
            contentValues
        ) ?: error("Failed to create MediaStore record")



        val csvContent = buildString {
            appendLine("index,avgRed,avgGreen,avgBlue,sdRed,avgLum")
            frames.forEachIndexed { index, frame ->
                appendLine(
                    listOf(
                        index,
                        frame.avgRed,
                        frame.avgGreen,
                        frame.avgBlue,
                        frame.sdRed,
                        frame.avgLum
                    ).joinToString(",")
                )
            }
        }

        resolver.openOutputStream(uri)?.use { output ->
            output.write(csvContent.toByteArray())
        }

        // Processing complete
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
                error = e.message ?: "Unknown error occurred"
            )
        )
    }
}