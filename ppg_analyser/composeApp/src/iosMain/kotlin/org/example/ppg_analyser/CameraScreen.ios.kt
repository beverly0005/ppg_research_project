package org.example.ppg_analyser

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.interop.UIKitView
import androidx.compose.ui.unit.dp
import kotlinx.cinterop.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import platform.AVFoundation.*
import platform.CoreGraphics.CGRectZero
import platform.Foundation.*
import platform.UIKit.UIView
import platform.darwin.NSObject

data class CameraDevice(
    val device: AVCaptureDevice,
    val displayName: String
)

enum class RecordingStatus {
    IDLE,
    PREPARING,
    RECORDING,
}

@OptIn(ExperimentalForeignApi::class, ExperimentalMaterial3Api::class)
@Composable
actual fun CameraScreen(onResultAvailable: (String) -> Unit) {
    MaterialTheme {
        val scope = rememberCoroutineScope()
        var recordingStatus by remember { mutableStateOf(RecordingStatus.IDLE) }
        var isTorchOn by remember { mutableStateOf(false) }
        val cameraController = remember { IOSCameraController() }

        // Get available cameras
        val availableCameras = remember { cameraController.getAvailableCameras() }
        var selectedCamera by remember { mutableStateOf(availableCameras.firstOrNull()) }
        var expanded by remember { mutableStateOf(false) }

        // Check if current camera has torch
        val hasTorch = remember(selectedCamera) {
            selectedCamera?.device?.hasTorch == true &&
                    selectedCamera?.device?.isTorchAvailable() == true
        }

        LaunchedEffect(Unit) {
            selectedCamera?.let { camera ->
                cameraController.setup(
                    onVideoRecorded = { videoUrl ->
                        onResultAvailable(videoUrl)
                    },
                    camera = camera.device
                )
            }
        }

        // Re-setup camera when selection changes
        LaunchedEffect(selectedCamera) {
            if (recordingStatus == RecordingStatus.IDLE) {
                selectedCamera?.let { camera ->
                    cameraController.setup(
                        onVideoRecorded = { videoUrl ->
                            onResultAvailable(videoUrl)
                        },
                        camera = camera.device
                    )
                    // Reset torch state when switching cameras
                    isTorchOn = false
                }
            }
        }

        // Toggle torch when state changes
        LaunchedEffect(isTorchOn) {
            cameraController.setTorch(isTorchOn)
        }

        Box(modifier = Modifier.fillMaxSize()) {
            // Camera preview
            UIKitView(
                factory = {
                    cameraController.previewView
                },
                modifier = Modifier.fillMaxSize(),
                update = { view ->
                    cameraController.updatePreviewLayerFrame(view.bounds)
                }
            )

            // Camera selection dropdown at the top
            Column(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(16.dp)
                    .fillMaxWidth(0.9f)
            ) {
                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = {
                        if (recordingStatus == RecordingStatus.IDLE) {
                            expanded = !expanded
                        }
                    }
                ) {
                    OutlinedTextField(
                        value = selectedCamera?.displayName ?: "Select Camera",
                        onValueChange = {},
                        readOnly = true,
                        trailingIcon = {
                            ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded)
                        },
                        colors = ExposedDropdownMenuDefaults.outlinedTextFieldColors(),
                        modifier = Modifier
                            .menuAnchor()
                            .fillMaxWidth(),
                        enabled = recordingStatus == RecordingStatus.IDLE
                    )

                    ExposedDropdownMenu(
                        expanded = expanded,
                        onDismissRequest = { expanded = false }
                    ) {
                        availableCameras.forEach { camera ->
                            DropdownMenuItem(
                                text = { Text(camera.displayName) },
                                onClick = {
                                    selectedCamera = camera
                                    expanded = false
                                },
                                contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding
                            )
                        }
                    }
                }

                // Torch toggle button (only if camera has torch)
                if (hasTorch) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(
                        onClick = {
                            isTorchOn = !isTorchOn
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = recordingStatus == RecordingStatus.IDLE
                    ) {
                        Text(if (isTorchOn) "Turn Flash Off" else "Turn Flash On")
                    }
                }
            }

            // Recording button at the bottom
            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Button(
                    onClick = {
                        scope.launch {
                            try {
                                if (recordingStatus == RecordingStatus.IDLE) {
                                    recordingStatus = RecordingStatus.PREPARING
                                    delay(3000)
                                    recordingStatus = RecordingStatus.RECORDING
                                    cameraController.startRecording()
                                    delay(10_000)
                                    cameraController.stopRecording()
                                    recordingStatus = RecordingStatus.IDLE
                                }
                            } catch (e: Exception) {
                                e.printStackTrace()
                                recordingStatus = RecordingStatus.IDLE
                            }
                        }
                    }
                ) {
                    Text(
                        when (recordingStatus) {
                            RecordingStatus.IDLE -> "Start 10s Recording"
                            RecordingStatus.PREPARING -> "Hold steady..."
                            RecordingStatus.RECORDING -> "Recording..."
                        }
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalForeignApi::class)
private class IOSCameraController {
    // Create a custom UIView that handles layoutSubviews
    private class CameraPreviewView(private val updateFrame: (CValue<platform.CoreGraphics.CGRect>) -> Unit) :
        UIView(CGRectZero.readValue()) {

        override fun layoutSubviews() {
            super.layoutSubviews()
            updateFrame(this.bounds)
        }
    }

    private var previewLayer: AVCaptureVideoPreviewLayer? = null
    val previewView: UIView
    private var captureSession: AVCaptureSession = AVCaptureSession()
    private var movieFileOutput: AVCaptureMovieFileOutput? = null
    private var onVideoRecorded: ((String) -> Unit)? = null
    private var recordingDelegate: RecordingDelegate? = null
    private var currentVideoDevice: AVCaptureDevice? = null

    init {
        previewView = CameraPreviewView { bounds ->
            previewLayer?.frame = bounds
        }
    }

    fun getAvailableCameras(): List<CameraDevice> {
        val cameras = mutableListOf<CameraDevice>()

        // Get discovery session for video devices
        val discoverySession = AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes(
            listOf(
                AVCaptureDeviceTypeBuiltInWideAngleCamera,
                AVCaptureDeviceTypeBuiltInUltraWideCamera,
                AVCaptureDeviceTypeBuiltInTelephotoCamera,
                AVCaptureDeviceTypeBuiltInDualCamera,
                AVCaptureDeviceTypeBuiltInDualWideCamera,
                AVCaptureDeviceTypeBuiltInTripleCamera
            ),
            AVMediaTypeVideo,
            AVCaptureDevicePositionUnspecified
        )

        discoverySession?.devices?.forEach { device ->
            val captureDevice = device as? AVCaptureDevice
            captureDevice?.let {
                val position = when (it.position) {
                    AVCaptureDevicePositionFront -> "Front"
                    AVCaptureDevicePositionBack -> "Back"
                    else -> "Unknown"
                }

                val deviceType = when (it.deviceType) {
                    AVCaptureDeviceTypeBuiltInWideAngleCamera -> "Wide"
                    AVCaptureDeviceTypeBuiltInUltraWideCamera -> "Ultra Wide"
                    AVCaptureDeviceTypeBuiltInTelephotoCamera -> "Telephoto"
                    AVCaptureDeviceTypeBuiltInDualCamera -> "Dual"
                    AVCaptureDeviceTypeBuiltInDualWideCamera -> "Dual Wide"
                    AVCaptureDeviceTypeBuiltInTripleCamera -> "Triple"
                    else -> "Camera"
                }

                val displayName = "$position $deviceType"
                cameras.add(CameraDevice(it, displayName))
            }
        }

        return cameras
    }

    fun setup(onVideoRecorded: (String) -> Unit, camera: AVCaptureDevice) {
        this.onVideoRecorded = onVideoRecorded

        // Stop existing session
        captureSession.stopRunning()

        // Remove all inputs and outputs
        captureSession.inputs.forEach { input ->
            captureSession.removeInput(input as AVCaptureInput)
        }
        captureSession.outputs.forEach { output ->
            captureSession.removeOutput(output as AVCaptureOutput)
        }

        captureSession.sessionPreset = AVCaptureSessionPresetHigh

        // Use the provided camera
        currentVideoDevice = camera
        val videoInput = AVCaptureDeviceInput.deviceInputWithDevice(camera, null) as? AVCaptureDeviceInput
        videoInput?.let { input ->
            if (captureSession.canAddInput(input)) {
                captureSession.addInput(input)
            }
        }
        enableAutofocus()
        enableAutoExposure()

        // Add audio input
        val audioDevice = AVCaptureDevice.defaultDeviceWithMediaType(AVMediaTypeAudio)
        audioDevice?.let { device ->
            val audioInput = AVCaptureDeviceInput.deviceInputWithDevice(device, null) as? AVCaptureDeviceInput
            audioInput?.let { input ->
                if (captureSession.canAddInput(input)) {
                    captureSession.addInput(input)
                }
            }
        }

        movieFileOutput = AVCaptureMovieFileOutput()
        movieFileOutput?.let { output ->
            if (captureSession.canAddOutput(output)) {
                captureSession.addOutput(output)
            }
        }

        // Remove old preview layer if exists
        previewLayer?.removeFromSuperlayer()

        // Create new preview layer
        previewLayer = AVCaptureVideoPreviewLayer(session = captureSession).apply {
            videoGravity = AVLayerVideoGravityResizeAspectFill
            frame = previewView.bounds
        }
        previewView.layer.addSublayer(previewLayer!!)

        captureSession.startRunning()
    }

    fun enableAutofocus() {
        currentVideoDevice?.let { device ->
            try {
                device.lockForConfiguration(null)

                // Check if continuous autofocus is supported
                if (device.isFocusModeSupported(AVCaptureFocusModeContinuousAutoFocus)) {
                    device.focusMode = AVCaptureFocusModeContinuousAutoFocus
                    println("Autofocus enabled: Continuous AutoFocus")
                } else if (device.isFocusModeSupported(AVCaptureFocusModeAutoFocus)) {
                    device.focusMode = AVCaptureFocusModeAutoFocus
                    println("Autofocus enabled: AutoFocus")
                } else {
                    println("Autofocus not supported on this device")
                }

                device.unlockForConfiguration()
            } catch (e: Exception) {
                println("Error enabling autofocus: $e")
            }
        }
    }

    fun enableAutoExposure() {
        currentVideoDevice?.let { device ->
            try {
                device.lockForConfiguration(null)

                // Check if continuous auto exposure is supported
                if (device.isExposureModeSupported(AVCaptureExposureModeContinuousAutoExposure)) {
                    device.exposureMode = AVCaptureExposureModeContinuousAutoExposure
                    println("Auto exposure enabled: Continuous Auto Exposure")
                } else if (device.isExposureModeSupported(AVCaptureExposureModeAutoExpose)) {
                    device.exposureMode = AVCaptureExposureModeAutoExpose
                    println("Auto exposure enabled: Auto Expose")
                } else {
                    println("Auto exposure not supported on this device")
                }

                device.unlockForConfiguration()
            } catch (e: Exception) {
                println("Error enabling auto exposure: $e")
            }
        }
    }

    fun setTorch(on: Boolean) {
        currentVideoDevice?.let { device ->
            // Check if device has torch
            if (device.hasTorch && device.isTorchAvailable()) {
                try {
                    device.lockForConfiguration(null)
                    if (on) {
                        device.torchMode = AVCaptureTorchModeOn
                    } else {
                        device.torchMode = AVCaptureTorchModeOff
                    }
                    device.unlockForConfiguration()
                } catch (e: Exception) {
                    println("Error setting torch: $e")
                }
            }
        }
    }

    fun updatePreviewLayerFrame(bounds: CValue<platform.CoreGraphics.CGRect>) {
        previewLayer?.frame = bounds
    }

    fun startRecording() {
        val outputURL = createOutputURL()
        recordingDelegate = RecordingDelegate(onVideoRecorded)
        movieFileOutput?.startRecordingToOutputFileURL(outputURL, recordingDelegate!!)
    }

    fun stopRecording() {
        movieFileOutput?.stopRecording()
    }

    private fun createOutputURL(): NSURL {
        val documentsPath = NSSearchPathForDirectoriesInDomains(
            NSDocumentDirectory,
            NSUserDomainMask,
            true
        ).firstOrNull() as? String ?: ""

        val timestamp = NSDate().timeIntervalSince1970.toLong()
        val fileName = "video_$timestamp.mov"
        val filePath = "$documentsPath/$fileName"

        return NSURL.fileURLWithPath(filePath)
    }

    private class RecordingDelegate(
        private val onVideoRecorded: ((String) -> Unit)?
    ) : NSObject(), AVCaptureFileOutputRecordingDelegateProtocol {

        override fun captureOutput(
            output: AVCaptureFileOutput,
            didFinishRecordingToOutputFileAtURL: NSURL,
            fromConnections: List<*>,
            error: NSError?
        ) {
            if (error == null) {
                onVideoRecorded?.invoke(didFinishRecordingToOutputFileAtURL.absoluteString ?: "")
            } else {
                println("Recording error: ${error.localizedDescription}")
            }
        }
    }
}