import { SmallWebRTCTransport } from 'pipecat-client-web-transports/transports/small-webrtc-transport/src';
import { RTVIMessage, TransportState } from '@pipecat-ai/client-js';

// Use type assertions to bypass strict type checking
type AnyOptions = any;

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
    username: 'a4eb45b8d331e70a3a2830fc',
    credential: 'JPSRWezq5gzaVIe8'
  }
];

// API endpoint
const API_URL = 'http://localhost:8000/offer';

// WebRTC Transport
let transport: SmallWebRTCTransport | null = null;

// Audio data
let audioChunks: ArrayBuffer[] = [];
let receivedAudioChunks: ArrayBuffer[] = [];
let isReceivingAudio = false;
let totalAudioSize = 0;
let receivedAudioSize = 0;

// Log messages to the UI
function log(message: string): void {
  const logEntry = document.createElement('div');
  logEntry.textContent = `${new Date().toLocaleTimeString()}: ${message}`;
  logOutput.appendChild(logEntry);
  logOutput.scrollTop = logOutput.scrollHeight;
  console.log(message);
}

// Update connection status in the UI
function updateConnectionStatus(status: string, connected: boolean): void {
  connectionStatus.textContent = status;
  connectionStatus.className = connected ? 'status-indicator connected' : 'status-indicator';
  connectButton.disabled = connected;
  disconnectButton.disabled = !connected;
  sendAudioButton.disabled = !connected || !audioFileInput.files?.length;
}

// Initialize the WebRTC transport
function initializeTransport(): void {
  transport = new SmallWebRTCTransport({
    iceServers,
    waitForICEGathering: true
  });

  transport.initialize(
    {
      transport: {} as any, // Add transport property with type assertion
      callbacks: {
        onConnected: () => {
          log('WebRTC connection established');
          updateConnectionStatus('Connected', true);
          transport?.sendReadyMessage();
        },
        onDisconnected: () => {
          log('WebRTC connection disconnected');
          updateConnectionStatus('Disconnected', false);
        },
        onTransportStateChanged: (state: TransportState) => {
          log(`Transport state changed: ${state}`);
        },
        onTrackStarted: (track: MediaStreamTrack) => {
          log(`Track started: ${track.kind}`);
        }
      },
      params: {
        baseUrl: API_URL,
        endpoints: {
          connect: ''
        }
      }
    } as any, // Type assertion to bypass strict type checking
    handleMessage
  );
}

// Handle incoming messages
function handleMessage(message: RTVIMessage): void {
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
    
    if (!transport) {
      initializeTransport();
    }
    
    await transport?.initDevices();
    await transport?.connect(null, new AbortController());
    
  } catch (error) {
    log(`Connection error: ${error}`);
    updateConnectionStatus('Connection Failed', false);
  }
}

// Disconnect from the WebRTC server
async function disconnect(): Promise<void> {
  try {
    log('Disconnecting...');
    await transport?.disconnect();
    transport = null;
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
  if (!transport || !audioFileInput.files?.length) {
    return;
  }

  const file = audioFileInput.files[0];
  log(`Sending audio file: ${file.name} (${file.size} bytes)`);
  
  try {
    const audioData = await readAudioFile(file);
    const chunkSize = 16 * 1024; // 16KB chunks
    const totalChunks = Math.ceil(audioData.byteLength / chunkSize);
    
    // Send start message with metadata
    transport.sendMessage({
      id: 'audio-start',
      type: 'audio-start',
      label: 'rtvi-ai',
      data: {
        filename: file.name,
        fileSize: audioData.byteLength,
        mimeType: file.type,
        totalChunks
      }
    } as any);
    
    // Send audio data in chunks
    for (let i = 0; i < totalChunks; i++) {
      const start = i * chunkSize;
      const end = Math.min(start + chunkSize, audioData.byteLength);
      const chunk = audioData.slice(start, end);
      
      transport.sendMessage({
        id: 'audio-chunk',
        type: 'audio-chunk',
        label: 'rtvi-ai',
        data: {
          chunkIndex: i,
          totalChunks,
          chunk: Array.from(new Uint8Array(chunk))
        }
      } as any);
      
      // Update progress bar
      const progress = Math.round((i + 1) / totalChunks * 100);
      sendProgress.style.width = `${progress}%`;
      
      // Small delay to prevent overwhelming the connection
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    // Send end message
    transport.sendMessage({
      id: 'audio-end',
      type: 'audio-end',
      label: 'rtvi-ai',
      data: {
        filename: file.name
      }
    } as any);
    
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
  sendAudioButton.disabled = !audioFileInput.files?.length || !transport || transport.state !== 'connected';
});

// Initialize the application
updateConnectionStatus('Disconnected', false);
log('WebRTC Audio Connection initialized');