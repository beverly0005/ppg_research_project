package org.example.ppg_analyser
data class RGBFrameEval(
    val avgRed: Float,
    val avgGreen: Float,
    val avgBlue: Float,
    val sdRed: Float,
    val avgLum: Float,
) {
    fun isAcceptable(): Boolean {
        return avgRed >= 240 && sdRed <= 20 && avgGreen <= 1 && avgBlue <= 75
    }
}

expect class VideoFrameExtractor(context: Any) {
    suspend fun extractFrames(videoUri: String): List<RGBFrameEval>
}