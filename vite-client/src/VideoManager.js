/**
 * VideoManager.js
 * 
 * Centralized video handling for both local and bot videos.
 * This class manages video elements, tracks, and streams for both the local user and the bot.
 */
class VideoManager {
  /**
   * Create a new VideoManager
   * @param {Object} rtviClient - The RTVI client instance
   * @param {Object} options - Configuration options
   */
  constructor(rtviClient, options = {}) {
    this.rtviClient = rtviClient;
    this.options = {
      debug: true,
      ...options
    };
    
    // Video elements and containers
    this.localVideoContainer = document.getElementById('local-video-container');
    this.botVideoContainer = document.getElementById('bot-video-container');
    this.cameraControlsContainer = document.getElementById('camera-controls');
    this.localVideo = null;
    this.botVideo = null;
    this.toggleBtn = null;
    
    // State tracking
    this.localVideoEnabled = false;
    this._localStream = null;
    
    // Initialize video elements
    this.createVideoElements();
    
    // Create camera toggle button
    this.createCameraToggleButton();
    
    // Debug logging
    this.log('VideoManager initialized');
  }
  
  /**
   * Create video elements for both local and bot videos
   */
  createVideoElements() {
    // Clear containers
    this.localVideoContainer.innerHTML = '';
    this.botVideoContainer.innerHTML = '';
    
    // Create local video element
    this.localVideo = document.createElement('video');
    this.localVideo.id = 'local-video';
    this.localVideo.autoplay = true;
    this.localVideo.playsInline = true;
    this.localVideo.muted = true;
    this.localVideo.style.width = '100%';
    this.localVideo.style.height = '100%';
    this.localVideo.style.objectFit = 'cover';
    this.localVideoContainer.appendChild(this.localVideo);
    
    // Create bot video element
    this.botVideo = document.createElement('video');
    this.botVideo.id = 'bot-video';
    this.botVideo.autoplay = true;
    this.botVideo.playsInline = true;
    this.botVideo.muted = true;
    this.botVideo.style.width = '100%';
    this.botVideo.style.height = '100%';
    this.botVideo.style.objectFit = 'cover';
    this.botVideoContainer.appendChild(this.botVideo);
    
    this.log('Video elements created');
  }
  
  /**
   * Create camera toggle button
   */
  createCameraToggleButton() {
    if (!this.cameraControlsContainer) {
      this.log('Camera controls container not found', 'warn');
      return;
    }
    
    // Clear any existing content
    this.cameraControlsContainer.innerHTML = '';
    
    // Create toggle button
    this.toggleBtn = document.createElement('button');
    this.toggleBtn.id = 'camera-toggle-btn';
    this.toggleBtn.className = 'control-btn';
    this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
    
    // Add event listener
    this.toggleBtn.addEventListener('click', () => this.toggleLocalCamera());
    
    // Append to container
    this.cameraControlsContainer.appendChild(this.toggleBtn);
    
    this.log('Camera toggle button created');
  }
  
  /**
   * Toggle the local camera on/off
   * @returns {Promise<boolean>} True if camera was enabled successfully, false otherwise
   */
  async toggleLocalCamera() {
    try {
      const tracks = this.rtviClient.tracks();
      const localVideoTrack = tracks.local?.video;
      
      if (this.localVideoEnabled && localVideoTrack) {
        // Disable camera
        localVideoTrack.enabled = false;
        this.localVideoEnabled = false;
        
        // Update button text
        if (this.toggleBtn) {
          this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
        }
        
        this.log('Local camera disabled');
        return false;
      } else {
        // Enable camera
        if (!localVideoTrack) {
          try {
            this.log('Requesting camera access...');
            
            // Request camera access through the browser
            const stream = await navigator.mediaDevices.getUserMedia({ 
              video: { 
                width: { ideal: 1280 },
                height: { ideal: 720 }
              } 
            });
            
            // Store the stream for later use
            this._localStream = stream;
            
            // Update the local video element with this stream
            this.localVideo.srcObject = stream;
            
            // Ensure the video plays
            try {
              await this.localVideo.play();
              this.log('Local video playback started');
            } catch (playError) {
              this.log('Error playing local video: ' + playError.message, 'error');
            }
            
            // Get the video track from the stream
            const videoTrack = stream.getVideoTracks()[0];
            
            // Log the track for debugging
            this.log(`Video track obtained: ${videoTrack.id}, ${videoTrack.label}`);
            this.log('Video track settings: ' + JSON.stringify(videoTrack.getSettings()));
            
          } catch (permissionError) {
            this.log('Camera permission error: ' + permissionError.message, 'error');
            this.showPermissionError(permissionError);
            return false; // Exit early if permission denied
          }
        } else {
          // Enable existing track
          this.log('Enabling existing video track');
          localVideoTrack.enabled = true;
        }
        
        // Update button text
        if (this.toggleBtn) {
          this.toggleBtn.innerHTML = '<span>Disable Camera</span>';
        }
        
        this.localVideoEnabled = true;
        return true;
      }
    } catch (error) {
      this.log('Error toggling camera: ' + error.message, 'error');
      this.showPermissionError(error);
      return false;
    }
  }
  
  /**
   * Set up the bot video track for display
   * @param {MediaStreamTrack} track - The bot's video track
   */
  /**
   * Display permission error message
   * @param {Error} error - The error that occurred
   */
  showPermissionError(error) {
    this.log('Camera permission error details: ' + JSON.stringify(error), 'error');
    
    // Find the camera controls container
    const container = this.cameraControlsContainer;
    if (!container) {
      this.log('Cannot show error: camera controls container not found', 'error');
      return;
    }
    
    // Remove any existing error messages
    const existingErrors = container.querySelectorAll('.error-message');
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
    container.appendChild(errorMsg);
    
    // Add a retry button
    const retryBtn = document.createElement('button');
    retryBtn.className = 'retry-btn';
    retryBtn.textContent = 'Retry';
    retryBtn.addEventListener('click', () => {
      errorMsg.remove();
      retryBtn.remove();
      this.toggleLocalCamera();
    });
    
    container.appendChild(retryBtn);
  }
  
  /**
   * Set up the bot video track for display
   * @param {MediaStreamTrack} track - The bot's video track
   */
  async setupBotVideoTrack(track) {
    this.log('Setting up bot video track');
    
    // Check if we're already displaying this track
    if (this.botVideo.srcObject) {
      const oldTrack = this.botVideo.srcObject.getVideoTracks()[0];
      if (oldTrack?.id === track.id) {
        this.log('Bot video track already set up');
        return;
      }
    }
    
    // Create a new MediaStream with the track and set it as the video source
    const mediaStream = new MediaStream([track]);
    this.botVideo.srcObject = mediaStream;
    
    try {
      await this.botVideo.play();
      this.log('Bot video playback started');
    } catch (playError) {
      this.log('Error playing bot video: ' + playError.message, 'error');
    }
  }
  
  /**
   * Set up the bot audio track for playback
   * @param {MediaStreamTrack} track - The bot's audio track
   * @param {HTMLAudioElement} audioElement - The audio element to use
   */
  setupBotAudioTrack(track, audioElement) {
    this.log('Setting up bot audio track');
    
    // Check if we're already playing this track
    if (audioElement.srcObject) {
      const oldTrack = audioElement.srcObject.getAudioTracks()[0];
      if (oldTrack?.id === track.id) {
        this.log('Bot audio track already set up');
        return;
      }
    }
    
    // Create a new MediaStream with the track and set it as the audio source
    audioElement.srcObject = new MediaStream([track]);
  }
  
  /**
   * Check for available media tracks and set them up if present
   * @param {HTMLAudioElement} botAudio - The audio element for bot audio
   */
  setupMediaTracks(botAudio) {
    if (!this.rtviClient) return;
    
    // Get current tracks from the client
    const tracks = this.rtviClient.tracks();
    this.log('Available tracks: ' + JSON.stringify(Object.keys(tracks)));
    
    // Set up any available bot tracks
    if (tracks.bot?.audio) {
      this.setupBotAudioTrack(tracks.bot.audio, botAudio);
    }
    
    if (tracks.bot?.video) {
      this.setupBotVideoTrack(tracks.bot.video);
    }
  }
  
  /**
   * Set up listeners for track events (start/stop)
   * @param {HTMLAudioElement} botAudio - The audio element for bot audio
   */
  setupTrackListeners(botAudio) {
    if (!this.rtviClient) return;
    
    const RTVIEvent = this.rtviClient.constructor.RTVIEvent;
    
    // Listen for new tracks starting
    this.rtviClient.on(RTVIEvent.TrackStarted, (track, participant) => {
      // Only handle non-local (bot) tracks
      if (!participant?.local) {
        if (track.kind === 'audio') {
          this.setupBotAudioTrack(track, botAudio);
        } else if (track.kind === 'video') {
          this.setupBotVideoTrack(track);
        }
      }
    });
    
    // Listen for tracks stopping
    this.rtviClient.on(RTVIEvent.TrackStopped, (track, participant) => {
      this.log(
        `Track stopped event: ${track.kind} from ${
          participant?.name || 'unknown'
        }`
      );
    });
  }
  
  /**
   * Clean up resources when disconnecting
   */
  cleanup() {
    // Clean up bot video
    if (this.botVideo?.srcObject) {
      this.botVideo.srcObject.getTracks().forEach((track) => track.stop());
      this.botVideo.srcObject = null;
    }
    
    // Clean up local video
    if (this.localVideo?.srcObject) {
      this.localVideo.srcObject.getTracks().forEach((track) => track.stop());
      this.localVideo.srcObject = null;
    }
    
    // Stop any tracks in the local stream
    if (this._localStream) {
      this._localStream.getTracks().forEach(track => track.stop());
      this._localStream = null;
    }
    
    // Reset state
    this.localVideoEnabled = false;
    
    // Reset button text
    if (this.toggleBtn) {
      this.toggleBtn.innerHTML = '<span>Enable Camera</span>';
    }
    
    this.log('Video resources cleaned up');
  }
  
  /**
   * Log a message with optional level
   * @param {string} message - The message to log
   * @param {string} level - Log level (log, warn, error)
   */
  log(message, level = 'log') {
    if (!this.options.debug) return;
    
    const prefix = '[VideoManager]';
    
    switch (level) {
      case 'warn':
        console.warn(`${prefix} ${message}`);
        break;
      case 'error':
        console.error(`${prefix} ${message}`);
        break;
      default:
        console.log(`${prefix} ${message}`);
    }
  }
}

export default VideoManager;