/**
 * RTVI Client Implementation
 *
 * This client connects to an RTVI-compatible bot server using WebRTC (via Daily).
 * It handles audio/video streaming and manages the connection lifecycle.
 *
 * Requirements:
 * - A running RTVI bot server (defaults to http://localhost:7860)
 * - The server must implement the /connect endpoint that returns Daily.co room credentials
 * - Browser with WebRTC support
 */

import { RTVIClient, RTVIEvent } from '@pipecat-ai/client-js';
import { DailyTransport } from '@pipecat-ai/daily-transport';

/**
 * ChatbotClient handles the connection and media management for a real-time
 * voice and video interaction with an AI bot.
 */
class ChatbotClient {
  constructor() {
    // Initialize client state
    this.rtviClient = null;
    this.cameraToggle = null;
    this.setupDOMElements();
    this.setupEventListeners();
    this.initializeClientAndTransport();
    
    // Initialize camera toggle immediately
    this.initializeCameraToggle();
  }

  /**
   * Set up references to DOM elements and create necessary media elements
   */
  setupDOMElements() {
    // Get references to UI control elements
    this.connectBtn = document.getElementById('connect-btn');
    this.disconnectBtn = document.getElementById('disconnect-btn');
    this.statusSpan = document.getElementById('connection-status');
    this.debugLog = document.getElementById('debug-log');
    this.botVideoContainer = document.getElementById('bot-video-container');

    // Get reference to the camera controls container
    this.cameraControlsContainer = document.getElementById('camera-controls');

    // Create an audio element for bot's voice output
    this.botAudio = document.createElement('audio');

    // Reduce Audio Latency on Client
    this.botAudio.setSinkId('default'); // For hardware acceleration if supported
    this.botAudio.preload = "auto";
    this.botAudio.defaultPlaybackRate = 1.0;

    this.botAudio.autoplay = true;
    this.botAudio.playsInline = true;
    document.body.appendChild(this.botAudio);
  }

  /**
   * Set up event listeners for connect/disconnect buttons
   */
  setupEventListeners() {
    this.connectBtn.addEventListener('click', () => this.connect());
    this.disconnectBtn.addEventListener('click', () => this.disconnect());
  }

  /**
   * Set up the RTVI client and Daily transport
   */
  initializeClientAndTransport() {
    const baseUrl = import.meta.env.VITE_BASE_URL || "http://localhost:8000";

    // Initialize the RTVI client with a DailyTransport and our configuration
    this.rtviClient = new RTVIClient({
      transport: new DailyTransport(),
      params: {
        // The baseURL and endpoint of your bot server that the client will connect to
        baseUrl: baseUrl,
        endpoints: {
          connect: '/connect',
        },
      },
      enableMic: true, // Enable microphone for user input
      enableCam: true,
      callbacks: {
        // Handle connection state changes
        onConnected: () => {
          this.updateStatus('Connected');
          this.connectBtn.disabled = true;
          this.disconnectBtn.disabled = false;
          this.log('Client connected');

          // Start periodic audio-level stats monitoring
          if (!this._statsInterval) {
            this._statsInterval = setInterval(() => {
              const call = this.rtviClient?.transport?._call;
              if (call?.getStats) {
                call.getStats().then(stats => {
                  // Optional: filter for audio levels or RTT here
                  this.log(`[Stats] Audio: ${JSON.stringify(stats, null, 2)}`);
                });
              }
            }, 5000); // every 5 seconds
          }
        },
        onDisconnected: () => {
          this.updateStatus('Disconnected');
          this.connectBtn.disabled = false;
          this.disconnectBtn.disabled = true;
          this.log('Client disconnected');

         if (this._statsInterval) {
            clearInterval(this._statsInterval);
            this._statsInterval = null;
          }
          
        },
        // Handle transport state changes
        onTransportStateChanged: (state) => {
          this.updateStatus(`Transport: ${state}`);
          this.log(`Transport state changed: ${state}`);
          if (state === 'ready') {
            this.setupMediaTracks();
          }
        },
        // Handle bot connection events
        onBotConnected: (participant) => {
          this.log(`Bot connected: ${JSON.stringify(participant)}`);
        },
        onBotDisconnected: (participant) => {
          this.log(`Bot disconnected: ${JSON.stringify(participant)}`);
        },
        onBotReady: (data) => {
          this.log(`Bot ready: ${JSON.stringify(data)}`);
          this.setupMediaTracks();
        },
        // Transcript events
        onUserTranscript: (data) => {
          // Only log final transcripts
          if (data.final) {
            this.log(`User: ${data.text}`);
          }
        },
        onBotTranscript: (data) => {
          this.log(`Bot: ${data.text}`);
        },
        // Error handling
        onMessageError: (error) => {
          console.log('Message error:', error);
        },
        onError: (error) => {
          console.log('Error:', JSON.stringify(error));
        },
      },
    });

    // Set up listeners for media track events
    this.setupTrackListeners();
  }

  /**
   * Add a timestamped message to the debug log
   */
  log(message) {
    const entry = document.createElement('div');
    entry.textContent = `${new Date().toISOString()} - ${message}`;

    // Add styling based on message type
    if (message.startsWith('User: ')) {
      entry.style.color = '#2196F3'; // blue for user
    } else if (message.startsWith('Bot: ')) {
      entry.style.color = '#4CAF50'; // green for bot
    }

    this.debugLog.appendChild(entry);
    this.debugLog.scrollTop = this.debugLog.scrollHeight;
    console.log(message);
  }

  /**
   * Update the connection status display
   */
  updateStatus(status) {
    this.statusSpan.textContent = status;
    this.log(`Status: ${status}`);
  }

  /**
   * Check for available media tracks and set them up if present
   * This is called when the bot is ready or when the transport state changes to ready
   */
  setupMediaTracks() {
    if (!this.rtviClient) return;

    // Get current tracks from the client
    const tracks = this.rtviClient.tracks();

    // Set up any available bot tracks
    if (tracks.bot?.audio) {
      this.setupAudioTrack(tracks.bot.audio);
    }
    if (tracks.bot?.video) {
      this.setupVideoTrack(tracks.bot.video);
    }
  }

  /**
   * Set up listeners for track events (start/stop)
   * This handles new tracks being added during the session
   */
  setupTrackListeners() {
    if (!this.rtviClient) return;

    // Listen for new tracks starting
    this.rtviClient.on(RTVIEvent.TrackStarted, (track, participant) => {
      // Only handle non-local (bot) tracks
      if (!participant?.local) {
        if (track.kind === 'audio') {
          this.setupAudioTrack(track);
        } else if (track.kind === 'video') {
          this.setupVideoTrack(track);
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
   * Set up an audio track for playback
   * Handles both initial setup and track updates
   */
  setupAudioTrack(track) {
    this.log('Setting up audio track');
    // Check if we're already playing this track
    if (this.botAudio.srcObject) {
      const oldTrack = this.botAudio.srcObject.getAudioTracks()[0];
      if (oldTrack?.id === track.id) return;
    }
    // Create a new MediaStream with the track and set it as the audio source
    this.botAudio.srcObject = new MediaStream([track]);
  }

  /**
   * Set up a video track for display
   * Handles both initial setup and track updates
   */
  setupVideoTrack(track) {
    this.log('Setting up video track');
    const videoEl = document.createElement('video');
    videoEl.autoplay = true;
    videoEl.playsInline = true;
    videoEl.muted = true;
    videoEl.style.width = '100%';
    videoEl.style.height = '100%';
    videoEl.style.objectFit = 'cover';

    // Check if we're already displaying this track
    if (this.botVideoContainer.querySelector('video')?.srcObject) {
      const oldTrack = this.botVideoContainer
        .querySelector('video')
        .srcObject.getVideoTracks()[0];
      if (oldTrack?.id === track.id) return;
    }

    // Create a new MediaStream with the track and set it as the video source
    videoEl.srcObject = new MediaStream([track]);
    this.botVideoContainer.innerHTML = '';
    this.botVideoContainer.appendChild(videoEl);
  }

  /**
   * Initialize and connect to the bot
   * First enables the camera, then initializes devices and establishes the connection
   */
  async connect() {
    try {
      // First enable the camera and wait for it to load
      this.log('Enabling camera...');
      if (!this.cameraToggle) {
        this.log('Camera toggle not initialized yet, initializing now...');
        await this.initializeCameraToggle(true); // Wait for initialization
      }
      
      // Enable camera and wait for it to be ready
      const cameraEnabled = await this.cameraToggle.toggleCamera();
      
      if (!cameraEnabled) {
        this.log('Failed to enable camera, cannot proceed with connection');
        this.updateStatus('Camera Error');
        return;
      }
      
      this.log('Camera enabled successfully, proceeding with connection');
      
      // Initialize audio/video devices
      this.log('Initializing devices...');
      await this.rtviClient.initDevices();

      // Connect to the bot
      this.log('Connecting to bot...');
      await this.rtviClient.connect();

      this.log('Connection complete');
    } catch (error) {
      // Handle any errors during connection
      this.log(`Error connecting: ${error.message}`);
      this.log(`Error stack: ${error.stack}`);
      this.updateStatus('Error');

      // Clean up if there's an error
      if (this.rtviClient) {
        try {
          await this.rtviClient.disconnect();
        } catch (disconnectError) {
          this.log(`Error during disconnect: ${disconnectError.message}`);
        }
      }
    }
  }

  /**
   * Disconnect from the bot and clean up media resources
   */
  async disconnect() {
    if (this.rtviClient) {
      try {
        // Disconnect the RTVI client
        await this.rtviClient.disconnect();

        // Clean up audio
        if (this.botAudio.srcObject) {
          this.botAudio.srcObject.getTracks().forEach((track) => track.stop());
          this.botAudio.srcObject = null;
        }

        // Clean up video
        if (this.botVideoContainer.querySelector('video')?.srcObject) {
          const video = this.botVideoContainer.querySelector('video');
          video.srcObject.getTracks().forEach((track) => track.stop());
          video.srcObject = null;
        }
        this.botVideoContainer.innerHTML = '';

        // Clean up camera toggle if it exists
        if (this.cameraToggle) {
          this.cameraToggle.cleanup();
        }
        
        // Clean up local video as fallback
        if (document.querySelector('#local-video-container video')?.srcObject) {
          const video = document.querySelector('#local-video-container video');
          video.srcObject.getTracks().forEach((track) => track.stop());
          video.srcObject = null;
        }
      } catch (error) {
        this.log(`Error disconnecting: ${error.message}`);
      }
    }
  }

  /**
   * Initialize the camera toggle component
   * @param {boolean} waitForInit - Whether to wait for initialization to complete
   * @returns {Promise<void>} - Promise that resolves when initialization is complete
   */
  async initializeCameraToggle(waitForInit = false) {
    try {
      // Import the CameraToggle module
      const module = await import('./CameraToggle.js');
      const CameraToggle = module.default;
      
      // Create the CameraToggle instance
      this.cameraToggle = new CameraToggle(this.rtviClient, this.cameraControlsContainer);
      
      this.log('Camera toggle initialized');
      return this.cameraToggle;
    } catch (error) {
      this.log(`Error loading CameraToggle: ${error.message}`);
      throw error;
    }
  }
}

// Initialize the client when the page loads
window.addEventListener('DOMContentLoaded', () => {
  new ChatbotClient();
});
