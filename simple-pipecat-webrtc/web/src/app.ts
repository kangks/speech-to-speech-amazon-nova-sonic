// DOM Elements
const connectionToggleButton = document.getElementById('connectionToggleButton') as HTMLButtonElement;
const startRecordingButton = document.getElementById('startRecordingButton') as HTMLButtonElement;
const stopRecordingButton = document.getElementById('stopRecordingButton') as HTMLButtonElement;
const pushToTalkButton = document.getElementById('pushToTalkButton') as HTMLButtonElement;
const alwaysListeningToggle = document.getElementById('alwaysListeningToggle') as HTMLInputElement;
const recordingIndicator = document.getElementById('recordingIndicator') as HTMLDivElement;
const audioPlayer = document.getElementById('audioPlayer') as HTMLAudioElement;
const connectionStatus = document.getElementById('connectionStatus') as HTMLDivElement;
const aiStatusIndicator = document.getElementById('aiStatusIndicator') as HTMLDivElement;
const conversationContainer = document.getElementById('conversationContainer') as HTMLDivElement;
const logOutput = document.getElementById('logOutput') as HTMLDivElement;
const sendProgress = document.getElementById('sendProgress') as HTMLDivElement;
const receiveProgress = document.getElementById('receiveProgress') as HTMLDivElement;
const interruptButton = document.getElementById('interruptButton') as HTMLButtonElement;
const modeManualRadio = document.getElementById('modeManual') as HTMLInputElement;
const modePushToTalkRadio = document.getElementById('modePushToTalk') as HTMLInputElement;

// WebRTC Configuration
const iceServers = [
  { urls: 'stun:stun.metered.ca:80' },
  {
    urls: 'turn:13.212.32.98:3478',
    username: 'user1',
    credential: 'pass1'
  }
];

// API endpoint
const API_URL = 'http://localhost:8000/offer';
// const API_URL = "https://nova-api.apse1.richardkang.aws.sg-pod-1.cs.doit-playgrounds.dev/offer";


// WebRTC Connection
let peerConnection: RTCPeerConnection | null = null;
let dataChannel: RTCDataChannel | null = null;
let pcId: string | null = null;

// Audio data
let receivedAudioChunks: ArrayBuffer[] = [];
let isReceivingAudio = false;
let totalAudioSize = 0;
let receivedAudioSize = 0;

// Microphone recording
let mediaStream: MediaStream | null = null;
let mediaRecorder: MediaRecorder | null = null;
let audioContext: AudioContext | null = null;
let isRecording = false;
let recordedChunks: Blob[] = [];
let recordingInterval: number | null = null;
let chunkIndex = 0;
let totalChunksEstimate = 0;

// Voice Activity Detection
let audioWorkletNode: AudioWorkletNode | null = null;
let vadActive = false;
let vadSilenceTimeout: number | null = null;
const VAD_THRESHOLD = 0.015; // Adjust based on testing
const VAD_SILENCE_PERIOD = 1500; // 1.5 seconds of silence before stopping

// Conversation state
enum AIState {
  IDLE = 'idle',
  LISTENING = 'listening',
  THINKING = 'thinking',
  SPEAKING = 'speaking'
}
let aiState: AIState = AIState.IDLE;
let isAISpeaking = false;
let conversationHistory: {role: 'user' | 'ai', text?: string, timestamp: number}[] = [];
let currentUserSpeech = '';
let currentAIResponse = '';

// Interaction modes
enum InteractionMode {
  MANUAL = 'manual',
  PUSH_TO_TALK = 'push-to-talk',
  ALWAYS_LISTENING = 'always-listening'
}
let interactionMode: InteractionMode = InteractionMode.MANUAL;
let isPushToTalkActive = false;

// Log messages to the UI
function log(message: string, level: 'info' | 'warn' | 'error' = 'info'): void {
  const logEntry = document.createElement('div');
  logEntry.textContent = `${new Date().toLocaleTimeString()}: ${message}`;
  
  // Add class based on log level
  if (level === 'warn') {
    logEntry.className = 'log-warning';
    console.warn(message);
  } else if (level === 'error') {
    logEntry.className = 'log-error';
    console.error(message);
  } else {
    console.log(message);
  }
  
  logOutput.appendChild(logEntry);
  logOutput.scrollTop = logOutput.scrollHeight;
}

// Update connection status in the UI
function updateConnectionStatus(status: string, connected: boolean): void {
  connectionStatus.textContent = status;
  connectionStatus.className = connected ? 'status-indicator connected' : 'status-indicator';
  
  // Update connection toggle button
  connectionToggleButton.textContent = connected ? 'Disconnect' : 'Connect';
  
  // Update recording buttons based on connection and interaction mode
  const isConnected = connected && !isRecording;
  startRecordingButton.disabled = !isConnected || interactionMode !== InteractionMode.MANUAL;
  stopRecordingButton.disabled = !connected || !isRecording;
  pushToTalkButton.disabled = !isConnected || interactionMode !== InteractionMode.PUSH_TO_TALK;
  alwaysListeningToggle.disabled = !isConnected;
  interruptButton.disabled = !isConnected || !isAISpeaking;
}

// Update AI status in the UI
function updateAIStatus(state: AIState): void {
  aiState = state;
  aiStatusIndicator.textContent = `AI: ${state.charAt(0).toUpperCase() + state.slice(1)}`;
  
  // Remove all state classes
  aiStatusIndicator.classList.remove('ai-idle', 'ai-listening', 'ai-thinking', 'ai-speaking');
  
  // Add the appropriate state class
  aiStatusIndicator.classList.add(`ai-${state}`);
  
  // Update interrupt button state
  interruptButton.disabled = state !== AIState.SPEAKING;
}

// Add message to conversation UI
function addConversationMessage(role: 'user' | 'ai', text: string): void {
  // Create message element
  const messageElement = document.createElement('div');
  messageElement.className = `conversation-message ${role}-message`;
  
  // Create avatar
  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}-avatar`;
  avatar.textContent = role === 'user' ? '👤' : '🤖';
  
  // Create message content
  const content = document.createElement('div');
  content.className = 'message-content';
  content.textContent = text;
  
  // Add elements to message
  messageElement.appendChild(avatar);
  messageElement.appendChild(content);
  
  // Add to conversation container
  conversationContainer.appendChild(messageElement);
  
  // Scroll to bottom
  conversationContainer.scrollTop = conversationContainer.scrollHeight;
  
  // Add to history
  conversationHistory.push({
    role,
    text,
    timestamp: Date.now()
  });
}

// Initialize WebRTC connection
async function initializeConnection(): Promise<void> {
  try {
    // Create peer connection with ICE servers
    log('Creating RTCPeerConnection with ICE servers:');
    iceServers.forEach(server => {
      log(`- ${JSON.stringify(server)}`);
    });
    
    peerConnection = new RTCPeerConnection({
      iceServers,
      iceCandidatePoolSize: 10
    });
    
    // Set up ICE candidate handling
    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        log(`Generated ICE candidate: ${event.candidate.candidate.substring(0, 50)}...`);
      } else {
        log('ICE candidate generation complete');
      }
    };
    
    peerConnection.oniceconnectionstatechange = () => {
      log(`ICE connection state changed: ${peerConnection?.iceConnectionState}`);
      
      if (peerConnection?.iceConnectionState === 'connected' ||
          peerConnection?.iceConnectionState === 'completed') {
        updateConnectionStatus('Connected', true);
      } else if (peerConnection?.iceConnectionState === 'failed' ||
                peerConnection?.iceConnectionState === 'disconnected' ||
                peerConnection?.iceConnectionState === 'closed') {
        updateConnectionStatus('Connection Failed', false);
        log(`ICE connection failed: ${peerConnection.iceConnectionState}`, 'error');
      }
    };
    
    peerConnection.onicegatheringstatechange = () => {
      log(`ICE gathering state changed: ${peerConnection?.iceGatheringState}`);
    };
    
    peerConnection.onsignalingstatechange = () => {
      log(`Signaling state changed: ${peerConnection?.signalingState}`);
    };
    
    peerConnection.onconnectionstatechange = () => {
      log(`Connection state changed: ${peerConnection?.connectionState}`);
    };
    
    // Create data channel
    log('Creating data channel');
    dataChannel = peerConnection.createDataChannel('audio-channel', {
      ordered: true
    });
    
    // Set up data channel event handlers
    dataChannel.onopen = async () => {
      log('Data channel opened');
      updateConnectionStatus('Connected', true);
      
      // Request microphone access as soon as connection is established
      const micAccessGranted = await requestMicrophoneAccess();
      if (!micAccessGranted) {
        log('Microphone access denied. Voice functionality will be limited.', 'warn');
      } else {
        log('Microphone access granted after connection established');
      }
      
      // Send ready message
      sendMessage({
        type: 'client-ready',
        label: 'rtvi-ai',
        data: {}
      });
    };
    
    dataChannel.onclose = () => {
      log('Data channel closed');
      updateConnectionStatus('Disconnected', false);
    };
    
    dataChannel.onerror = (error) => {
      log(`Data channel error: ${error}`, 'error');
    };
    
    dataChannel.onmessage = (event) => {
      const message = JSON.parse(event.data);
      handleMessage(message);
    };
    
    // Create offer with proper constraints
    log('Creating offer');
    const offerOptions = {
      offerToReceiveAudio: false,
      offerToReceiveVideo: false
    };
    
    const offer = await peerConnection.createOffer(offerOptions);
    log(`Created offer: ${offer.type}`);
    
    // Set local description
    log('Setting local description');
    await peerConnection.setLocalDescription(offer);
    log(`Local description set: ${peerConnection.signalingState}`);
    
    // Wait for ICE gathering to complete or timeout after 5 seconds
    await new Promise<void>((resolve) => {
      const checkState = () => {
        if (peerConnection?.iceGatheringState === 'complete') {
          log('ICE gathering complete');
          resolve();
        }
      };
      
      const gatheringTimeout = setTimeout(() => {
        log('ICE gathering timed out, proceeding with available candidates', 'warn');
        resolve();
      }, 5000);
      
      if (peerConnection) {
        peerConnection.onicegatheringstatechange = () => {
          log(`ICE gathering state changed: ${peerConnection?.iceGatheringState}`);
          checkState();
        };
      }
      
      checkState();
    });
    
    // Get the current offer with ICE candidates
    const currentOffer = peerConnection.localDescription;
    if (!currentOffer) {
      throw new Error('No local description available');
    }
    
    // Send offer to server
    log('Sending offer to server');
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        sdp: currentOffer.sdp,
        type: currentOffer.type,
        pc_id: pcId
      })
    });
    
    if (!response.ok) {
      throw new Error(`Server responded with status: ${response.status}`);
    }
    
    // Process answer
    const answer = await response.json();
    log(`Received answer from server: ${answer.type}`);
    
    // Store the pc_id if provided
    if (answer.pc_id) {
      pcId = answer.pc_id;
      log(`Received pc_id: ${pcId}`);
    }
    
    // Set remote description
    log('Setting remote description');
    await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
    log(`Remote description set: ${peerConnection.signalingState}`);
    
    log('WebRTC connection initialized');
  } catch (error) {
    log(`Error initializing connection: ${error}`, 'error');
    updateConnectionStatus('Connection Failed', false);
    
    // Clean up on error
    if (dataChannel) {
      dataChannel.close();
      dataChannel = null;
    }
    
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
  }
}

// Send message over data channel
function sendMessage(message: any): void {
  if (dataChannel && dataChannel.readyState === 'open') {
    dataChannel.send(JSON.stringify(message));
  } else {
    log('Cannot send message: Data channel not open');
  }
}

// Handle incoming messages
function handleMessage(message: any): void {
  log(`Received message: ${message.type}`);
  
  if (message.type === 'audio-chunk') {
    handleAudioChunk(message.data);
  } else if (message.type === 'audio-start') {
    startReceivingAudio(message.data);
    
    // Update AI state to speaking
    updateAIStatus(AIState.SPEAKING);
    isAISpeaking = true;
    
    // If there's text in the response, add it to the conversation
    if (message.data.text) {
      currentAIResponse = message.data.text;
      addConversationMessage('ai', message.data.text);
    }
  } else if (message.type === 'audio-end') {
    finishReceivingAudio();
    
    // Update AI state to idle
    updateAIStatus(AIState.IDLE);
    isAISpeaking = false;
    currentAIResponse = '';
    
    // If in always listening mode, start listening again
    if (interactionMode === InteractionMode.ALWAYS_LISTENING && !isRecording) {
      startContinuousListening();
    }
  } else if (message.type === 'transcription') {
    // Handle transcription of user speech
    if (message.data.text) {
      currentUserSpeech = message.data.text;
      
      // If we're still recording, this is a partial transcription
      if (!isRecording) {
        addConversationMessage('user', message.data.text);
      }
    }
  }
}

// Connect to the WebRTC server
async function connect(): Promise<void> {
  try {
    log('Initializing WebRTC connection...');
    updateConnectionStatus('Connecting...', false);
    
    // Check STUN/TURN server accessibility
    log('Checking STUN/TURN server accessibility...');
    try {
      const stunCheckPc = new RTCPeerConnection({ iceServers });
      stunCheckPc.createDataChannel('stun-check');
      
      const stunOffer = await stunCheckPc.createOffer();
      await stunCheckPc.setLocalDescription(stunOffer);
      
      // Wait briefly to see if we get any ICE candidates
      await new Promise<void>((resolve) => {
        let candidatesFound = false;
        
        stunCheckPc.onicecandidate = (event) => {
          if (event.candidate) {
            candidatesFound = true;
            log(`STUN/TURN check: Found candidate type: ${event.candidate.type}`);
          }
        };
        
        setTimeout(() => {
          if (!candidatesFound) {
            log('STUN/TURN check: No ICE candidates found, servers may be unreachable', 'warn');
          } else {
            log('STUN/TURN check: ICE candidates found, servers appear reachable');
          }
          stunCheckPc.close();
          resolve();
        }, 2000);
      });
    } catch (stunError) {
      log(`STUN/TURN check failed: ${stunError}`, 'warn');
    }
    
    await initializeConnection();
    
    // Request microphone access after WebRTC connection is established
    if (peerConnection && peerConnection.connectionState === 'connected') {
      const micAccessGranted = await requestMicrophoneAccess();
      if (!micAccessGranted) {
        log('Microphone access denied. Voice functionality will be limited.', 'warn');
      } else {
        log('Microphone access granted after connection established');
      }
    }
  } catch (error) {
    log(`Connection error: ${error}`, 'error');
    updateConnectionStatus('Connection Failed', false);
  }
}

// Disconnect from the WebRTC server
async function disconnect(): Promise<void> {
  try {
    log('Disconnecting...');
    
    // Stop recording if active
    if (isRecording) {
      await stopRecording();
    }
    
    // Stop audio playback if active
    if (audioPlayer.src) {
      audioPlayer.pause();
      audioPlayer.src = '';
    }
    
    // Close data channel
    if (dataChannel) {
      dataChannel.close();
      dataChannel = null;
    }
    
    // Close peer connection
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    
    // Stop microphone stream
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    
    // Close audio context
    if (audioContext && audioContext.state !== 'closed') {
      await audioContext.close();
      audioContext = null;
      audioWorkletNode = null;
    }
    
    // Reset state variables
    pcId = null;
    isRecording = false;
    vadActive = false;
    isAISpeaking = false;
    
    // Update UI
    updateConnectionStatus('Disconnected', false);
    updateAIStatus(AIState.IDLE);
    recordingIndicator.textContent = 'Not Recording';
    recordingIndicator.classList.remove('active');
    
    log('Disconnected successfully');
  } catch (error) {
    log(`Disconnection error: ${error}`, 'error');
  }
}

// Request microphone access
async function requestMicrophoneAccess(): Promise<boolean> {
  try {
    log('Requesting microphone access...');
    
    // Request microphone access with audio processing options
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      },
      video: false
    });
    
    log('Microphone access granted');
    
    // Initialize audio context if needed
    if (!audioContext) {
      audioContext = new AudioContext();
    }
    
    // Set up voice activity detection
    await setupVoiceActivityDetection();
    
    return true;
  } catch (error) {
    log(`Error accessing microphone: ${error}`, 'error');
    return false;
  }
}

// Set up voice activity detection
async function setupVoiceActivityDetection(): Promise<void> {
  if (!audioContext || !mediaStream) return;
  
  try {
    // Load audio worklet for VAD
    await audioContext.audioWorklet.addModule('./src/vad-processor.js');
    
    // Create source from microphone
    const micSource = audioContext.createMediaStreamSource(mediaStream);
    
    // Create VAD worklet node with parameters
    audioWorkletNode = new AudioWorkletNode(audioContext, 'vad-processor', {
      parameterData: {
        // You can adjust these parameters if needed
        silenceThreshold: VAD_THRESHOLD,
        voiceDetectionThreshold: 3,
        silenceDetectionThreshold: 5
      }
    });
    
    // Connect nodes
    micSource.connect(audioWorkletNode);
    
    // Reset VAD state
    vadActive = false;
    
    // Listen for VAD messages
    audioWorkletNode.port.onmessage = (event) => {
      const { vadActive: isActive, volume } = event.data;
      
      if (isActive !== vadActive) {
        vadActive = isActive;
        
        if (vadActive) {
          // Voice detected
          log(`Voice activity detected (volume: ${volume.toFixed(3)})`);
          
          // Clear silence timeout if it exists
          if (vadSilenceTimeout !== null) {
            clearTimeout(vadSilenceTimeout);
            vadSilenceTimeout = null;
          }
          
          // If in always listening mode and not already recording, start recording
          if (interactionMode === InteractionMode.ALWAYS_LISTENING && !isRecording) {
            startRecording();
          }
          
          // Visual indicator for voice activity
          recordingIndicator.classList.add('voice-active');
        } else {
          // Silence detected
          log(`Silence detected (volume: ${volume.toFixed(3)})`);
          
          // If in always listening mode and recording, set timeout to stop recording
          if (interactionMode === InteractionMode.ALWAYS_LISTENING && isRecording) {
            vadSilenceTimeout = window.setTimeout(() => {
              log('Silence period exceeded, stopping recording');
              stopRecording();
              vadSilenceTimeout = null;
            }, VAD_SILENCE_PERIOD);
          }
          
          // Remove visual indicator for voice activity
          recordingIndicator.classList.remove('voice-active');
        }
      }
    };
    
    log('Voice activity detection set up successfully');
  } catch (error) {
    log(`Error setting up voice activity detection: ${error}`, 'error');
  }
}

// Start continuous listening mode
function startContinuousListening(): void {
  if (!mediaStream || isRecording) return;
  
  log('Starting continuous listening mode');
  
  // Set up VAD if not already done
  if (!audioWorkletNode) {
    setupVoiceActivityDetection();
  }
  
  // VAD will automatically trigger recording when voice is detected
  updateAIStatus(AIState.IDLE);
}

// Start recording from microphone
async function startRecording(): Promise<void> {
  if (isRecording || !dataChannel || dataChannel.readyState !== 'open') {
    return;
  }
  
  try {
    // Ensure we have microphone access
    if (!mediaStream) {
      log('No microphone access. Cannot start recording.', 'error');
      return;
    }
    
    // Initialize audio context if needed
    if (!audioContext) {
      audioContext = new AudioContext();
    }
    
    // Reset recording state
    recordedChunks = [];
    chunkIndex = 0;
    isRecording = true;
    currentUserSpeech = '';
    
    // Update UI
    recordingIndicator.textContent = 'Recording';
    recordingIndicator.classList.add('active');
    startRecordingButton.disabled = true;
    stopRecordingButton.disabled = false;
    
    // Update AI state
    updateAIStatus(AIState.LISTENING);
    
    log('Starting microphone recording...');
    
    // Create media recorder
    if (!mediaStream) {
      throw new Error('MediaStream is null');
    }
    
    mediaRecorder = new MediaRecorder(mediaStream, {
      mimeType: 'audio/webm;codecs=opus'
    });
    
    // Send audio-start message
    sendMessage({
      type: 'audio-start',
      label: 'rtvi-ai',
      data: {
        filename: 'microphone-recording.webm',
        fileSize: 0, // Unknown at this point
        mimeType: 'audio/webm;codecs=opus',
        totalChunks: 0, // Unknown at this point
        continuous: true // Indicate this is part of a continuous conversation
      }
    });
    
    // Handle data available event
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
        processAndSendAudioChunk(event.data);
      }
    };
    
    // Start recording with smaller chunks for lower latency
    mediaRecorder.start(500);
    
    log('Microphone recording started');
  } catch (error) {
    log(`Error starting recording: ${error}`, 'error');
    isRecording = false;
    recordingIndicator.textContent = 'Not Recording';
    recordingIndicator.classList.remove('active');
    startRecordingButton.disabled = false;
    stopRecordingButton.disabled = true;
    updateAIStatus(AIState.IDLE);
  }
}

// Process and send audio chunk
async function processAndSendAudioChunk(blob: Blob): Promise<void> {
  try {
    // Convert blob to array buffer
    const arrayBuffer = await blob.arrayBuffer();
    
    // Only send audio when VAD detects voice activity
    if (vadActive) {
      // Send chunk
      sendMessage({
        type: 'audio-chunk',
        label: 'rtvi-ai',
        data: {
          chunkIndex: chunkIndex++,
          totalChunks: totalChunksEstimate,
          chunk: Array.from(new Uint8Array(arrayBuffer))
        }
      });
      
      // Update progress (approximate since we don't know total size)
      const progress = Math.min(95, (chunkIndex / (totalChunksEstimate || 20)) * 100);
      sendProgress.style.width = `${progress}%`;
      
      log(`Sent audio chunk ${chunkIndex} (voice detected)`);
    } else {
      // Skip sending when no voice is detected
      log('Skipped sending audio chunk (no voice detected)');
    }
  } catch (error) {
    log(`Error processing audio chunk: ${error}`, 'error');
  }
}

// Stop recording and send final audio
async function stopRecording(): Promise<void> {
  if (!isRecording || !mediaRecorder) {
    return;
  }
  
  try {
    log('Stopping microphone recording...');
    
    // Stop the media recorder
    mediaRecorder.stop();
    
    // Update UI
    isRecording = false;
    recordingIndicator.textContent = 'Not Recording';
    recordingIndicator.classList.remove('active');
    
    // Update button states based on interaction mode
    if (interactionMode === InteractionMode.MANUAL) {
      startRecordingButton.disabled = false;
    } else if (interactionMode === InteractionMode.PUSH_TO_TALK) {
      pushToTalkButton.disabled = false;
    }
    
    stopRecordingButton.disabled = true;
    
    // Update AI state
    updateAIStatus(AIState.THINKING);
    
    // Send audio-end message
    sendMessage({
      type: 'audio-end',
      label: 'rtvi-ai',
      data: {
        filename: 'microphone-recording.webm'
      }
    });
    
    // Reset progress bar
    sendProgress.style.width = '100%';
    setTimeout(() => {
      sendProgress.style.width = '0%';
    }, 1000);
    
    // Add user message to conversation (placeholder until we get actual transcription)
    if (recordedChunks.length > 0) {
      addConversationMessage('user', currentUserSpeech || '(Voice message)');
    }
    
    log('Microphone recording stopped and sent');
  } catch (error) {
    log(`Error stopping recording: ${error}`, 'error');
  }
}

// Start receiving audio
function startReceivingAudio(data: any): void {
  log(`Starting to receive audio: ${data.filename} (${data.fileSize} bytes)`);
  isReceivingAudio = true;
  receivedAudioChunks = [];
  totalAudioSize = data.fileSize;
  receivedAudioSize = 0;
}

// Handle incoming audio chunk
function handleAudioChunk(data: any): void {
  if (!isReceivingAudio) return;
  
  const { chunk, chunkIndex, totalChunks } = data;
  const arrayBuffer = new Uint8Array(chunk).buffer;
  receivedAudioChunks[chunkIndex] = arrayBuffer;
  receivedAudioSize += arrayBuffer.byteLength;
  
  // Update progress bar - handle case where totalAudioSize is unknown
  let progress = 0;
  if (totalAudioSize && totalAudioSize > 0) {
    progress = Math.round((receivedAudioSize / totalAudioSize) * 100);
  } else if (totalChunks && totalChunks > 0) {
    // Fallback to using chunk count if file size is unknown
    const receivedChunksCount = receivedAudioChunks.filter(chunk => chunk !== undefined).length;
    progress = Math.round((receivedChunksCount / totalChunks) * 100);
  } else {
    // If we don't know total size or chunks, show indeterminate progress
    progress = Math.min(95, receivedAudioChunks.length * 5); // Cap at 95%
  }
  
  receiveProgress.style.width = `${progress}%`;
  
  log(`Received chunk ${chunkIndex + 1}/${totalChunks || '?'} (${progress}% complete)`);
}

// Finish receiving audio and play it
function finishReceivingAudio(): void {
  if (!isReceivingAudio) return;
  
  log('Finished receiving audio');
  isReceivingAudio = false;
  
  // Filter out any undefined chunks (in case some chunks were missed)
  const validChunks = receivedAudioChunks.filter(chunk => chunk !== undefined);
  
  // Combine all valid chunks
  const totalLength = validChunks.reduce((total, chunk) => total + chunk.byteLength, 0);
  const combinedBuffer = new Uint8Array(totalLength);
  
  let offset = 0;
  for (const chunk of validChunks) {
    combinedBuffer.set(new Uint8Array(chunk), offset);
    offset += chunk.byteLength;
  }
  
  // Check if we have any audio data to play
  if (totalLength === 0 || receivedAudioChunks.length === 0) {
    log('No audio data received to play', 'warn');
    isAISpeaking = false;
    updateAIStatus(AIState.IDLE);
    return;
  }

  // Create blob with more flexible MIME type
  const blob = new Blob([combinedBuffer], { type: 'audio/webm;codecs=opus' });
  const audioUrl = URL.createObjectURL(blob);
  
  // Set audio source and add error handler
  audioPlayer.onerror = (e) => {
    log(`Audio element error: ${audioPlayer.error?.message || 'Unknown error'}`, 'error');
  };
  
  audioPlayer.src = audioUrl;
  
  // Play audio and handle any errors
  audioPlayer.play()
    .then(() => {
      log('Audio playback started');
      isAISpeaking = true;
      updateAIStatus(AIState.SPEAKING);
    })
    .catch(error => {
      log(`Audio playback error: ${error}`, 'error');
      
      // Try again with different MIME type as fallback
      const fallbackBlob = new Blob([combinedBuffer], { type: 'audio/wav' });
      const fallbackUrl = URL.createObjectURL(fallbackBlob);
      audioPlayer.src = fallbackUrl;
      
      audioPlayer.play()
        .then(() => {
          log('Audio playback started with fallback format');
          isAISpeaking = true;
          updateAIStatus(AIState.SPEAKING);
        })
        .catch(fallbackError => {
          log(`Fallback audio playback also failed: ${fallbackError}`, 'error');
          isAISpeaking = false;
          updateAIStatus(AIState.IDLE);
        });
    });
    
  // Clean up old audio URLs to prevent memory leaks
  setTimeout(() => {
    URL.revokeObjectURL(audioUrl);
  }, 30000); // Revoke after 30 seconds
  
  // Reset progress bar
  receiveProgress.style.width = '0%';
}

// Handle push-to-talk button
function handlePushToTalk(isDown: boolean): void {
  if (!dataChannel || dataChannel.readyState !== 'open') return;
  
  if (isDown && !isRecording) {
    // Start recording when button is pressed
    isPushToTalkActive = true;
    startRecording();
  } else if (!isDown && isRecording && isPushToTalkActive) {
    // Stop recording when button is released
    isPushToTalkActive = false;
    stopRecording();
  }
}

// Change interaction mode
function setInteractionMode(mode: InteractionMode): void {
  // Stop any current recording
  if (isRecording) {
    stopRecording();
  }
  
  interactionMode = mode;
  log(`Interaction mode changed to: ${mode}`);
  
  // Update UI
  document.querySelectorAll('.mode-indicator').forEach(el => el.classList.remove('active'));
  document.querySelector(`.mode-${mode}`)?.classList.add('active');
  
  // Update button states
  startRecordingButton.disabled = mode !== InteractionMode.MANUAL;
  pushToTalkButton.disabled = mode !== InteractionMode.PUSH_TO_TALK;
  alwaysListeningToggle.checked = mode === InteractionMode.ALWAYS_LISTENING;
  
  // Start continuous listening if in always listening mode
  if (mode === InteractionMode.ALWAYS_LISTENING) {
    startContinuousListening();
  }
}

// Interrupt AI response
function interruptAIResponse(): void {
  if (!isAISpeaking) return;
  
  log('Interrupting AI response');
  
  // Send interrupt message
  sendMessage({
    type: 'interrupt',
    label: 'rtvi-ai',
    data: {}
  });
  
  // Stop audio playback
  audioPlayer.pause();
  
  // Update UI
  isAISpeaking = false;
  updateAIStatus(AIState.IDLE);
  
  // If in always listening mode, start listening again
  if (interactionMode === InteractionMode.ALWAYS_LISTENING) {
    startContinuousListening();
  }
}

// Event listeners
connectionToggleButton.addEventListener('click', () => {
  if (peerConnection && dataChannel) {
    disconnect();
  } else {
    connect();
  }
});
startRecordingButton.addEventListener('click', startRecording);
stopRecordingButton.addEventListener('click', stopRecording);
interruptButton.addEventListener('click', interruptAIResponse);

// Push-to-talk event listeners
pushToTalkButton.addEventListener('mousedown', () => handlePushToTalk(true));
pushToTalkButton.addEventListener('mouseup', () => handlePushToTalk(false));
pushToTalkButton.addEventListener('mouseleave', () => handlePushToTalk(false));
pushToTalkButton.addEventListener('touchstart', (e) => {
  e.preventDefault();
  handlePushToTalk(true);
});
pushToTalkButton.addEventListener('touchend', (e) => {
  e.preventDefault();
  handlePushToTalk(false);
});

// Mode selection event listeners
modeManualRadio.addEventListener('change', () => {
  if (modeManualRadio.checked) {
    setInteractionMode(InteractionMode.MANUAL);
  }
});

modePushToTalkRadio.addEventListener('change', () => {
  if (modePushToTalkRadio.checked) {
    setInteractionMode(InteractionMode.PUSH_TO_TALK);
  }
});

// Always listening toggle
alwaysListeningToggle.addEventListener('change', () => {
  if (alwaysListeningToggle.checked) {
    setInteractionMode(InteractionMode.ALWAYS_LISTENING);
  } else {
    setInteractionMode(InteractionMode.MANUAL);
  }
});

// Audio player events
audioPlayer.addEventListener('play', () => {
  isAISpeaking = true;
  updateAIStatus(AIState.SPEAKING);
});

audioPlayer.addEventListener('pause', () => {
  isAISpeaking = false;
  updateAIStatus(AIState.IDLE);
});

audioPlayer.addEventListener('ended', () => {
  isAISpeaking = false;
  updateAIStatus(AIState.IDLE);
  
  // If in always listening mode, start listening again
  if (interactionMode === InteractionMode.ALWAYS_LISTENING) {
    startContinuousListening();
  }
});

// Initialize the application
updateConnectionStatus('Disconnected', false);
updateAIStatus(AIState.IDLE);
log('WebRTC Audio Connection initialized');

// Check for microphone support
if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
  log('Your browser does not support microphone access. Please use a modern browser like Chrome or Firefox.', 'error');
}