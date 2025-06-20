// DOM Elements
const connectButton = document.getElementById('connectButton') as HTMLButtonElement;
const disconnectButton = document.getElementById('disconnectButton') as HTMLButtonElement;
const sendAudioButton = document.getElementById('sendAudioButton') as HTMLButtonElement;
const audioFileInput = document.getElementById('audioFileInput') as HTMLInputElement;
const audioPlayer = document.getElementById('audioPlayer') as HTMLAudioElement;
const connectionStatus = document.getElementById('connectionStatus') as HTMLDivElement;
const logOutput = document.getElementById('logOutput') as HTMLDivElement;
const sendProgress = document.getElementById('sendProgress') as HTMLDivElement;
const receiveProgress = document.getElementById('receiveProgress') as HTMLDivElement;

// WebRTC Configuration
const iceServers = [
  { urls: 'stun:stun.metered.ca:80' },
  {
    urls: 'turn:sg.relay.metered.ca:80',
    username: '<enact>',
    credential: '<enact>'
  }
];

// API endpoint
const API_URL = 'http://localhost:8000/offer';

// WebRTC Connection
let peerConnection: RTCPeerConnection | null = null;
let dataChannel: RTCDataChannel | null = null;
let pcId: string | null = null;

// Audio data
let audioChunks: ArrayBuffer[] = [];
let receivedAudioChunks: ArrayBuffer[] = [];
let isReceivingAudio = false;
let totalAudioSize = 0;
let receivedAudioSize = 0;

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
  connectButton.disabled = connected;
  disconnectButton.disabled = !connected;
  sendAudioButton.disabled = !connected || !audioFileInput.files?.length;
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
    dataChannel.onopen = () => {
      log('Data channel opened');
      updateConnectionStatus('Connected', true);
      
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
  } else if (message.type === 'audio-end') {
    finishReceivingAudio();
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
  } catch (error) {
    log(`Connection error: ${error}`, 'error');
    updateConnectionStatus('Connection Failed', false);
  }
}

// Disconnect from the WebRTC server
async function disconnect(): Promise<void> {
  try {
    log('Disconnecting...');
    
    if (dataChannel) {
      dataChannel.close();
      dataChannel = null;
    }
    
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    
    // Reset pc_id
    pcId = null;
    
    updateConnectionStatus('Disconnected', false);
  } catch (error) {
    log(`Disconnection error: ${error}`);
  }
}

// Read audio file and prepare for sending
async function readAudioFile(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

// Send audio file over WebRTC
async function sendAudio(): Promise<void> {
  if (!dataChannel || !audioFileInput.files?.length) {
    return;
  }

  const file = audioFileInput.files[0];
  log(`Sending audio file: ${file.name} (${file.size} bytes)`);
  
  try {
    const audioData = await readAudioFile(file);
    const chunkSize = 16 * 1024; // 16KB chunks
    const totalChunks = Math.ceil(audioData.byteLength / chunkSize);
    
    // Send start message with metadata
    sendMessage({
      type: 'audio-start',
      label: 'rtvi-ai',
      data: {
        filename: file.name,
        fileSize: audioData.byteLength,
        mimeType: file.type,
        totalChunks
      }
    });
    
    // Send audio data in chunks
    for (let i = 0; i < totalChunks; i++) {
      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, audioData.byteLength);
      const chunk = audioData.slice(start, end);
      
      sendMessage({
        type: 'audio-chunk',
        label: 'rtvi-ai',
        data: {
          chunkIndex: i,
          totalChunks,
          chunk: Array.from(new Uint8Array(chunk))
        }
      });
      
      // Update progress bar
      const progress = Math.round((i + 1) / totalChunks * 100);
      sendProgress.style.width = `${progress}%`;
      
      // Small delay to prevent overwhelming the connection
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    // Send end message
    sendMessage({
      type: 'audio-end',
      label: 'rtvi-ai',
      data: {
        filename: file.name
      }
    });
    
    log('Audio file sent successfully');
  } catch (error) {
    log(`Error sending audio: ${error}`);
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
  
  // Update progress bar
  const progress = Math.round(receivedAudioSize / totalAudioSize * 100);
  receiveProgress.style.width = `${progress}%`;
  
  log(`Received chunk ${chunkIndex + 1}/${totalChunks} (${progress}% complete)`);
}

// Finish receiving audio and play it
function finishReceivingAudio(): void {
  if (!isReceivingAudio) return;
  
  log('Finished receiving audio');
  isReceivingAudio = false;
  
  // Combine all chunks
  const totalLength = receivedAudioChunks.reduce((total, chunk) => total + chunk.byteLength, 0);
  const combinedBuffer = new Uint8Array(totalLength);
  
  let offset = 0;
  for (const chunk of receivedAudioChunks) {
    combinedBuffer.set(new Uint8Array(chunk), offset);
    offset += chunk.byteLength;
  }
  
  // Create blob and play audio
  const blob = new Blob([combinedBuffer], { type: 'audio/wav' });
  const audioUrl = URL.createObjectURL(blob);
  audioPlayer.src = audioUrl;
  audioPlayer.play();
}

// Event listeners
connectButton.addEventListener('click', connect);
disconnectButton.addEventListener('click', disconnect);
sendAudioButton.addEventListener('click', sendAudio);
audioFileInput.addEventListener('change', () => {
  sendAudioButton.disabled = !audioFileInput.files?.length || !dataChannel || dataChannel.readyState !== 'open';
});

// Initialize the application
updateConnectionStatus('Disconnected', false);
log('WebRTC Audio Connection initialized');