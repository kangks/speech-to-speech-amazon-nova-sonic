/**
 * Camera Toggle Component
 * 
 * This component provides UI and functionality to toggle the user's webcam on/off.
 */
class CameraToggle {
  constructor(rtviClient, container) {
    this.rtviClient = rtviClient;
    this.container = container;
    this.isEnabled = false;
    this.createUI();
    this.setupEventListeners();
  }

  /**
   * Create the toggle button and local video preview
   */
  createUI() {
    // Create toggle button
    this.toggleBtn = document.createElement('button');
    this.toggleBtn.id = 'camera-toggle-btn';
    this.toggleBtn.className = 'control-btn';
    this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
    
    // Create local video container
    this.localVideoContainer = document.createElement('div');
    this.localVideoContainer.id = 'local-video-container';
    this.localVideoContainer.className = 'video-container local-video';
    this.localVideoContainer.style.display = 'none';
    
    // Create video element
    this.localVideo = document.createElement('video');
    this.localVideo.autoplay = true;
    this.localVideo.playsInline = true;
    this.localVideo.muted = true;
    this.localVideo.style.width = '100%';
    this.localVideo.style.height = '100%';
    this.localVideo.style.objectFit = 'cover';
    
    // Append elements
    this.localVideoContainer.appendChild(this.localVideo);
    this.container.appendChild(this.toggleBtn);
    this.container.appendChild(this.localVideoContainer);
  }

  /**
   * Set up event listeners for the toggle button
   */
  setupEventListeners() {
    this.toggleBtn.addEventListener('click', () => this.toggleCamera());
  }

  /**
   * Toggle the camera on/off
   */
  async toggleCamera() {
    try {
      const tracks = this.rtviClient.tracks();
      const localVideoTrack = tracks.local?.video;
      
      if (this.isEnabled && localVideoTrack) {
        // Disable camera by setting enabled to false
        localVideoTrack.enabled = false;
        this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
        this.localVideoContainer.style.display = 'none';
        this.isEnabled = false;
      } else {
        // If no track exists or it's disabled, we need to request camera access
        if (!localVideoTrack) {
          try {
            // Request camera access through the browser
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            
            // Store the stream for later use
            this._localStream = stream;
            
            // Update the local video element with this stream
            this.localVideo.srcObject = stream;
            
            // Get the video track from the stream
            const videoTrack = stream.getVideoTracks()[0];
            
            // Log the track for debugging
            console.log("Video track obtained:", videoTrack.id);
            
            // Note: We're not sending this to the transport yet as the API doesn't support it
            // The video is only displayed locally for now
          } catch (permissionError) {
            console.error('Camera permission error:', permissionError);
            this.showPermissionError(permissionError);
            return; // Exit early if permission denied
          }
        } else {
          // Enable existing track
          localVideoTrack.enabled = true;
        }
        
        this.toggleBtn.innerHTML = '<span>Disable Camera</span>';
        this.localVideoContainer.style.display = 'block';
        this.isEnabled = true;
        
        // Get the local video track and display it
        this.setupLocalVideoTrack();
      }
    } catch (error) {
      console.error('Error toggling camera:', error);
      this.showPermissionError(error);
    }
  }

  /**
   * Set up the local video track for display
   */
  setupLocalVideoTrack() {
    // If we have a local stream from getUserMedia, use that
    if (this._localStream) {
      this.localVideo.srcObject = this._localStream;
      return;
    }
    
    // Otherwise try to get the track from the rtviClient
    const tracks = this.rtviClient.tracks();
    if (tracks.local?.video) {
      this.localVideo.srcObject = new MediaStream([tracks.local.video]);
    }
  }

  /**
   * Display permission error message
   */
  showPermissionError(error) {
    console.error('Camera permission error details:', error);
    
    // Remove any existing error messages
    const existingErrors = this.container.querySelectorAll('.error-message');
    existingErrors.forEach(el => el.remove());
    
    // Create new error message with more details
    const errorMsg = document.createElement('div');
    errorMsg.className = 'error-message';
    
    // Determine the specific error message based on the error
    let errorText = 'Camera access denied. Please check your browser permissions.';
    
    if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
      errorText = 'Camera access was denied. Please allow camera access in your browser settings and try again.';
    } else if (error.name === 'NotFoundError') {
      errorText = 'No camera detected. Please connect a camera and try again.';
    } else if (error.name === 'NotReadableError' || error.name === 'AbortError') {
      errorText = 'Your camera is in use by another application. Please close other applications using your camera and try again.';
    } else if (error.name === 'OverconstrainedError') {
      errorText = 'Camera constraints cannot be satisfied. Please try a different camera.';
    } else if (error.name === 'TypeError') {
      errorText = 'Camera access is not supported in this browser or environment.';
    }
    
    errorMsg.textContent = errorText;
    this.container.appendChild(errorMsg);
    
    // Add a retry button
    const retryBtn = document.createElement('button');
    retryBtn.className = 'retry-btn';
    retryBtn.textContent = 'Retry';
    retryBtn.addEventListener('click', () => {
      errorMsg.remove();
      retryBtn.remove();
      this.toggleCamera();
    });
    
    this.container.appendChild(retryBtn);
  }
  
  /**
   * Clean up resources when disconnecting
   */
  cleanup() {
    // If there's a local video track, disable it
    try {
      const tracks = this.rtviClient.tracks();
      const localVideoTrack = tracks.local?.video;
      if (localVideoTrack && this.isEnabled) {
        localVideoTrack.enabled = false;
      }
    } catch (error) {
      console.error('Error disabling video track during cleanup:', error);
    }
    
    // Stop any tracks in the local stream
    if (this._localStream) {
      this._localStream.getTracks().forEach(track => track.stop());
      this._localStream = null;
    }
    
    // Clear the video element
    if (this.localVideo.srcObject) {
      this.localVideo.srcObject = null;
    }
    
    // Reset state
    this.isEnabled = false;
    this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
    this.localVideoContainer.style.display = 'none';
  }
}

export default CameraToggle;