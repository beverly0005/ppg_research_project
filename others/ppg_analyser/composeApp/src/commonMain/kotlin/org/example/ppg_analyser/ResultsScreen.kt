package org.example.ppg_analyser

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.patrykandpatrick.vico.compose.cartesian.CartesianChartHost
import com.patrykandpatrick.vico.compose.cartesian.axis.HorizontalAxis
import com.patrykandpatrick.vico.compose.cartesian.axis.VerticalAxis
import com.patrykandpatrick.vico.compose.cartesian.data.CartesianChartModelProducer
import com.patrykandpatrick.vico.compose.cartesian.data.CartesianLayerRangeProvider
import com.patrykandpatrick.vico.compose.cartesian.data.lineSeries
import com.patrykandpatrick.vico.compose.cartesian.layer.rememberLineCartesianLayer
import com.patrykandpatrick.vico.compose.cartesian.rememberCartesianChart


data class ProcessingState(
    val isProcessing: Boolean = false,
    val error: String? = null,
    val ppgSignals: List<RGBFrameEval>? = null
)


@Composable
expect fun ResultsScreen(videoUri: String): Unit

expect suspend fun processVideo(
    context: Any,
    videoUri: String,
    onUpdate: (ProcessingState) -> Unit
)

@Composable
fun ProcessingView(state: ProcessingState) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        CircularProgressIndicator()

        Text(
            text = "Processing Video",
            style = MaterialTheme.typography.titleMedium
        )
    }
}

@Composable
fun ErrorView(error: String) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
        modifier = Modifier.padding(32.dp)
    ) {
        Text(
            text = "Error Processing Video",
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.error
        )

        Text(
            text = error,
            style = MaterialTheme.typography.bodyMedium
        )
    }
}

@Composable
fun PPGLineChart(signals: List<Float>) {
    val modelProducer = remember { CartesianChartModelProducer() }

    // normalise signals
    val normalizedSignals = remember(signals) {
        if (signals.isEmpty()) return@remember emptyList<Float>()

        val min = signals.minOrNull() ?: 0f
        val max = signals.maxOrNull() ?: 0f
        val range = (max - min).takeIf { it != 0f } ?: 1f
        println("min: $min, max: $max, range: $range")

        signals.map { (it - min) / range }
    }

    println("normalizedSignals: $normalizedSignals")

    LaunchedEffect(normalizedSignals) {
        modelProducer.runTransaction {
            lineSeries { series(normalizedSignals) }
        }
    }

    CartesianChartHost(
        chart = rememberCartesianChart(
            rememberLineCartesianLayer(
                rangeProvider = remember {
                    CartesianLayerRangeProvider.fixed(minY = 0.0, maxY = 1.0)
                }
            ),
            startAxis = VerticalAxis.rememberStart(
                itemPlacer = VerticalAxis.ItemPlacer.step({ 0.2 })
            ),
            bottomAxis = HorizontalAxis.rememberBottom(
                itemPlacer = HorizontalAxis.ItemPlacer.aligned(
                    spacing = {1},
                    shiftExtremeLines = false
                )
            ),
        ),
        modelProducer = modelProducer,
    )
}

@Composable
fun ResultsView(signals: List<RGBFrameEval>) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "PPG Analysis Results",
            style = MaterialTheme.typography.titleLarge
        )

        // Check if video is usable
        fun isAcceptable(signals: List<RGBFrameEval>): Boolean {
            if (signals.isEmpty()) return false

            return signals.all { frame ->
                frame.isAcceptable()
            }
        }

        if (!isAcceptable(signals)) {
            Card { Text("Video did not meet usability conditions, please retake!") }
        }

        val limit = minOf(signals.size, 100)
        val first100RedValues = signals.take(limit).map{it.avgLum}
        Card(
            modifier = Modifier.fillMaxWidth()
        ) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("First $limit Red Values:")
                    // Joining the values into a readable string
                    Text(
                        text = first100RedValues.joinToString(separator = ", "),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        val ppgSignalValues = signals.map { it.avgLum }


        PPGLineChart(ppgSignalValues)
    }
}
