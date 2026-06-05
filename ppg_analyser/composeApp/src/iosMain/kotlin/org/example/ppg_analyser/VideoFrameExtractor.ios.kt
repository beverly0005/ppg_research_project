package org.example.ppg_analyser

import kotlinx.cinterop.CValue
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.free
import kotlinx.cinterop.nativeHeap
import kotlinx.cinterop.readValue
import kotlinx.cinterop.reinterpret
import platform.AVFoundation.*
import platform.CoreMedia.*
import platform.CoreGraphics.*
import platform.UIKit.*
import platform.Foundation.*
import kotlinx.coroutines.yield
import platform.darwin.ByteVar
import kotlin.math.sqrt
import kotlinx.cinterop.get
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import platform.QuartzCore.CACurrentMediaTime

actual class VideoFrameExtractor actual constructor(context: Any) {
    // Context is not used on iOS, but we keep the constructor to match the 'expect'

    @OptIn(ExperimentalForeignApi::class)
//    actual suspend fun extractFrames(videoUri: String): List<RGBFrameEval> {
//        val startTime = CACurrentMediaTime()
//        val frames = mutableListOf<RGBFrameEval>()
//
//        // Convert string URI to NSURL
//        val url = NSURL.URLWithString(videoUri) ?: return emptyList()
//        val asset = AVURLAsset.assetWithURL(url)
//        val imageGenerator = AVAssetImageGenerator(asset = asset).apply {
//            // Ensure we get frames as close to the requested time as possible
//            requestedTimeToleranceBefore = kCMTimeZero.readValue()
//            requestedTimeToleranceAfter = kCMTimeZero.readValue()
//            appliesPreferredTrackTransform = true
//        }
//
//        val durationSeconds = CMTimeGetSeconds(asset.duration)
//        val frameRate = (asset.tracksWithMediaType(AVMediaTypeVideo).first() as AVAssetTrack).nominalFrameRate()
//        val totalFrames = (durationSeconds * frameRate).toInt()
//
//        for (i in 0 until totalFrames) {
//            // Calculate time for this specific frame
//            val time = CMTimeMake(value = i.toLong(), timescale = frameRate.toInt())
//
//            // Generate the image synchronously (wrapped in loop)
//            val cgImage = imageGenerator.copyCGImageAtTime(time, actualTime = null, error = null)
//
//            cgImage?.let {
//                val eval = processCGImage(it)
//                frames.add(eval)
//            }
//
//            // Allow other coroutines to run (prevent UI freezing)
//            if (i % 10 == 0) yield()
//        }
//
//        val elapsedTime = CACurrentMediaTime() - startTime
//        println("Elapsed time: $elapsedTime")
//        return frames
//    }
    actual suspend fun extractFrames(videoUri: String): List<RGBFrameEval> {
        val startTime = CACurrentMediaTime()
        val frames = MutableList<RGBFrameEval?>(0) { null }

        val url = NSURL.URLWithString(videoUri) ?: return emptyList()
        val asset = AVURLAsset.assetWithURL(url)

        val imageGenerator = AVAssetImageGenerator(asset).apply {
            requestedTimeToleranceBefore = kCMTimeZero.readValue()
            requestedTimeToleranceAfter = kCMTimeZero.readValue()
            appliesPreferredTrackTransform = true
        }

        val durationSeconds = CMTimeGetSeconds(asset.duration)
        val track = asset.tracksWithMediaType(AVMediaTypeVideo).first() as AVAssetTrack
        val frameRate = track.nominalFrameRate
        val totalFrames = (durationSeconds * frameRate).toInt()

        // Pre-allocate for ordering
        frames.addAll(List(totalFrames) { null })

        coroutineScope {
            val jobs = mutableListOf<Deferred<Pair<Int, RGBFrameEval>?>>()

            for (i in 0 until totalFrames) {
                val time = CMTimeMake(
                    value = i.toLong(),
                    timescale = frameRate.toInt()
                )

                val cgImage = imageGenerator.copyCGImageAtTime(
                    time,
                    actualTime = null,
                    error = null
                )

                if (cgImage != null) {
                    jobs += async(Dispatchers.Default) {
                        i to processCGImage(cgImage)
                    }
                }

                // Yield occasionally to keep system responsive
                if (i % 10 == 0) yield()
            }

            jobs.awaitAll().forEach { result ->
                if (result != null) {
                    val (index, eval) = result
                    frames[index] = eval
                }
            }
        }

        val elapsed = CACurrentMediaTime() - startTime
        println("Elapsed time (iOS): $elapsed")

        return frames.filterNotNull()
    }

    @OptIn(ExperimentalForeignApi::class)
    private fun processCGImage(image: CGImageRef): RGBFrameEval {
        val width = CGImageGetWidth(image).toInt()
        val height = CGImageGetHeight(image).toInt()
        val bytesPerPixel = 4
        val bytesPerRow = width * bytesPerPixel
        val totalPixels = width * height

        // Create a buffer for the pixel data (RGBA)
        val colorSpace = CGColorSpaceCreateDeviceRGB()
//        val rawData = nativeHeap.allocArray<ByteVar>(totalPixels * bytesPerPixel)
//        val bitmapData = rawData.reinterpret<ByteVar>()
        val bitmapData = nativeHeap.allocArray<ByteVar>(totalPixels * bytesPerPixel)
        val context = CGBitmapContextCreate(
            data = bitmapData,
            width = width.toULong(),
            height = height.toULong(),
            bitsPerComponent = 8U,
            bytesPerRow = bytesPerRow.toULong(),
            space = colorSpace,
            bitmapInfo = CGImageAlphaInfo.kCGImageAlphaPremultipliedLast.value
        )

        CGContextDrawImage(context, CGRectMake(0.0, 0.0, width.toDouble(), height.toDouble()), image)

        var sumRed = 0.0
        var sumGreen = 0.0
        var sumBlue = 0.0
        var sumRedSq = 0.0
        var sumLum = 0.0

        for (i in 0 until totalPixels) {
            val offset = i * bytesPerPixel
            val r = (bitmapData[offset].toInt() and 0xFF).toDouble()
            val g = (bitmapData[offset + 1].toInt() and 0xFF).toDouble()
            val b = (bitmapData[offset + 2].toInt() and 0xFF).toDouble()

            // Luminance calculation: Y = 0.299R + 0.587G + 0.114B
            val l = (0.299 * r) + (0.587 * g) + (0.114 * b)

            sumRed += r
            sumGreen += g
            sumBlue += b
            sumRedSq += (r * r)
            sumLum += l
        }

        val avgR = (sumRed / totalPixels).toFloat()
        val avgG = (sumGreen / totalPixels).toFloat()
        val avgB = (sumBlue / totalPixels).toFloat()
        val avgLum = (sumLum / totalPixels).toFloat()

        val varianceRed = (sumRedSq / totalPixels) - (avgR.toDouble() * avgR.toDouble())
        val sdR = sqrt(maxOf(0.0, varianceRed)).toFloat()

        // Clean up native memory
        nativeHeap.free(bitmapData)
        CGContextRelease(context)
        CGColorSpaceRelease(colorSpace)

        return RGBFrameEval(
            avgRed = avgR,
            avgGreen = avgG,
            avgBlue = avgB,
            sdRed = sdR,
            avgLum = avgLum
        )
    }
}