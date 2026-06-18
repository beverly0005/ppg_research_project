package org.example.ppg_analyser

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.content.ContentUris
import androidx.annotation.RequiresApi
import androidx.core.graphics.blue
import androidx.core.graphics.green
import androidx.core.graphics.luminance
import androidx.core.graphics.red
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlin.math.sqrt


actual class VideoFrameExtractor actual constructor(context: Any) {
    // Just for matching contructor signature
    private val appContext = context as? Context
        ?: throw IllegalArgumentException("VideoFrameExtractor requires Android Context")

    @RequiresApi(Build.VERSION_CODES.P)
    actual suspend fun extractFrames(videoUri: String): List<RGBFrameEval> = withContext(Dispatchers.IO) {
        val startTime = System.nanoTime()


        val frames = mutableListOf<RGBFrameEval>()
        val retriever = MediaMetadataRetriever()

        try {
            val videoCollection =
                if (Build.VERSION.SDK_INT >= 29) {
                    MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL)
                } else {
                    MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                }

            val projection = arrayOf(MediaStore.Video.Media._ID)

            val videoUri = appContext.contentResolver.query(
                videoCollection,
                projection,
                "${MediaStore.Video.Media.SIZE} > 0",
                null,
                "${MediaStore.Video.Media.DATE_ADDED} DESC"
            )?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val id = cursor.getLong(
                        cursor.getColumnIndexOrThrow(MediaStore.Video.Media._ID)
                    )
                    ContentUris.withAppendedId(videoCollection, id)
                } else null
            }

            if (videoUri != null) {
                try {
                    delay(500)
                    println("videoUri:$videoUri")
                    retriever.setDataSource(appContext, videoUri)
                } catch (e: RuntimeException) {
                    println("Error with setDataSource:" + e.message)
                }
            } else {
                println("cannot find videos")
            }

            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLong() ?: 0L
            println("duration: $duration")
            val frameCount = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_FRAME_COUNT)?.toLong() ?: 0L
            val frameRate = frameCount * 1000L / duration
            println("frameRate: $frameRate")
            val interval = 1_000_000L / frameRate // microseconds

            val timestamps = mutableListOf<Long>()
            var currentTime = 0L

            while (currentTime < duration * 1000) {
                timestamps.add(currentTime)
                currentTime += interval
            }

            val semaphore = kotlinx.coroutines.sync.Semaphore(10) // NEVER > 2–3

            val deferred = timestamps.map { timeUs ->
                async(Dispatchers.IO) {
                    semaphore.acquire()
                    try {
                        val r = MediaMetadataRetriever()
                        r.setDataSource(appContext, videoUri)
                        val bmp = r.getFrameAtTime(timeUs, MediaMetadataRetriever.OPTION_CLOSEST)
                        r.release()

                        bmp?.let {
                            val eval = bitmapToRGBFrameEval(it)
                            it.recycle()
                            eval
                        }
                    } finally {
                        semaphore.release()
                    }
                }
            }

//            val poolSize = 5
//            val retrieverPool = ArrayDeque<MediaMetadataRetriever>(poolSize)
//
//            repeat(poolSize) {
//                val r = MediaMetadataRetriever()
//                r.setDataSource(appContext, videoUri)
//                retrieverPool.add(r)
//            }
//
//            val poolMutex = Mutex()
//
//            suspend fun acquireRetriever(): MediaMetadataRetriever {
//                while (true) {
//                    poolMutex.lock()
//                    val r = retrieverPool.removeFirstOrNull()
//                    poolMutex.unlock()
//
//
//                    if (r != null) return r
//                    delay(1) // avoid busy-spin
//                }
//            }
//
//
//            suspend fun releaseRetriever(r: MediaMetadataRetriever) {
//                poolMutex.lock()
//                retrieverPool.addLast(r)
//                poolMutex.unlock()
//            }
//
//            val deferred = timestamps.map { timeUs ->
//                async(Dispatchers.IO) {
//                    val r = acquireRetriever()
//                    try {
//                        val bmp = r.getFrameAtTime(
//                            timeUs,
//                            MediaMetadataRetriever.OPTION_CLOSEST
//                        )
//
//                        bmp?.let {
//                            val eval = bitmapToRGBFrameEval(it)
//                            it.recycle()
//                            eval
//                        }
//                    } finally {
//                        releaseRetriever(r)
//                    }
//                }
//            }

//            retrieverPool.forEach { it.release() }
//            retrieverPool.clear()

            val results = deferred.awaitAll().filterNotNull()
            frames.addAll(results)



            val elapsedTime = System.nanoTime() - startTime
            println("Elapsed time: $elapsedTime")
        } finally {
            retriever.release()
        }

        frames
    }

    private fun bitmapToRGBFrameEval(bitmap: Bitmap): RGBFrameEval {
        val width = bitmap.width
        val height = bitmap.height
        val numPixels = width * height
        val pixels = IntArray(numPixels)

        bitmap.getPixels(pixels, 0, width, 0, 0, width, height)

        var sumRed = 0.0
        var sumGreen = 0.0
        var sumBlue = 0.0
        var sumRedSq = 0.0
        var sumLum = 0.0

//        var intensityMax = Int.MIN_VALUE
//        var intensityMin = Int.MAX_VALUE
//        var intensityMin = Int.MAX_VALUE

        for (pixel in pixels) {
            // Extract channels using bit shifting

            // using RGB_565
            val r = pixel.red
            val g = pixel.green
            val b = pixel.blue
            val l = pixel.luminance

            sumRed += r
            sumGreen += g
            sumBlue += b
            sumRedSq += (r * r).toDouble()
            sumLum += l

//            val intensity = (r + g + b) / 3.0f
//            val intensity = r
//
//            if (intensity > intensityMax) intensityMax = intensity
//            if (intensity < intensityMin) intensityMin = intensity
        }

        val avgR = (sumRed / numPixels).toFloat()
        val avgG = (sumGreen / numPixels).toFloat()
        val avgB = (sumBlue / numPixels).toFloat()
        val avgLum = (sumLum / numPixels).toFloat()

        // Calculate Variance: Var = (SumSq / N) - (Mean^2)
        val varianceRed = (sumRedSq / numPixels) - (avgR.toDouble() * avgR.toDouble())
        val sdR = sqrt(maxOf(0.0, varianceRed)).toFloat()

//        val threshold = 5.5f * (intensityMax - intensityMin)
//        var ppgSignalValue = 0
//
//        for (pixel in pixels) {
//            val r = pixel.red
//
//            if (r > threshold) {
//                ppgSignalValue += 1
//            }
//        }

        return RGBFrameEval(
            avgRed = avgR,
            avgGreen = avgG,
            avgBlue = avgB,
            sdRed = sdR,
            avgLum = avgLum,
        )
    }
}