import './style.css';
import AudioPlayer from './helper/audioPlayer.js';
import S2sEvent from './helper/s2sEvents.js';
import { base64ToFloat32Array, arrayBufferToBase64 } from './helper/audioHelper.js';

// State variables
let socket = null;
let mediaRecorder = null;
let audioContext = null;
let audioPlayer = null;
let promptName = null;
let textContentName = null;
let audioContentName = null;
let chatMessages = {};

// DOM elements
const appElement = document.querySelector('#app');

// Create the UI
function createUI() {
  appElement.innerHTML = `
    <div class="container">
      <h1>Nova Sonic Speech-to-Speech</h1>
      
      <div class="controls">
        <button id="startButton" class="primary">Start Conversation</button>
      </div>
      
      <div class="conversation" id="conversation"></div>
      
      <div class="status" id="status">Initializing...</div>
    </div>
  `;
}

// Initialize the application
async function initApp() {
  // Create the UI
  createUI();
  
  // Add event listeners
  document.getElementById('startButton').addEventListener('click', handleSessionChange);
  
  // Initialize audio player
  audioPlayer = new AudioPlayer();
  try {
    await audioPlayer.start();
    console.log("Audio player initialized successfully");
    updateStatus("Ready");
  } catch (err) {
    console.error("Failed to initialize audio player:", err);
    updateStatus("Error initializing audio player");
  }
}

// Handle session change (start/stop)
async function handleSessionChange() {
  const startButton = document.getElementById('startButton');
  const isSessionActive = startButton.textContent === "End Conversation";
  
  console.log("Button clicked, session active:", isSessionActive);
  
  if (isSessionActive) {
    // End session
    endSession();
    audioPlayer.bargeIn();
    startButton.textContent = "Start Conversation";
    startButton.classList.remove('recording');
    updateStatus("Ready");
  } else {
    // Start session
    chatMessages = {};
    updateConversation();
    
    try {
      // Update UI first
      startButton.textContent = "End Conversation";
      startButton.classList.add('recording');
      updateStatus("Connecting...", "recording");
      
      // Connect WebSocket
      if (socket === null || socket.readyState !== WebSocket.OPEN) {
        await connectWebSocket();
      }
      
      // Start microphone
      await startMicrophone();
      
      updateStatus("Recording...", "recording");
    } catch (error) {
      console.error('Error starting session:', error);
      updateStatus("Error: " + error.message);
      startButton.textContent = "Start Conversation";
      startButton.classList.remove('recording');
    }
  }
}

// Connect to WebSocket server
async function connectWebSocket() {
  return new Promise((resolve, reject) => {
    // Generate UUIDs for the session
    promptName = crypto.randomUUID();
    textContentName = crypto.randomUUID();
    audioContentName = crypto.randomUUID();
    
    // Get WebSocket URL from environment or use default
    const wsUrl = import.meta.env.VITE_WEBSOCKET_URL || "ws://localhost:8081";
    console.log("Connecting to WebSocket:", wsUrl);
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
      console.log("WebSocket connected!");
      updateStatus("Connected", "connected");
      
      // Initialiez the session
      sendEvent(S2sEvent.init(promptName, textContentName, audioContentName));
      resolve();
    };
    
    // Handle connection errors
    socket.onerror = (error) => {
      console.error("WebSocket Error:", error);
      updateStatus("WebSocket Error", "disconnected");
      reject(error);
    };
    
    // Handle incoming messages
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data);
      handleIncomingMessage(event);
    };
    
    // Handle connection close
    socket.onclose = () => {
      console.log("WebSocket Disconnected");
      const startButton = document.getElementById('startButton');
      if (startButton && startButton.textContent === "End Conversation") {
        updateStatus("WebSocket Disconnected", "disconnected");
        // Reset UI
        startButton.textContent = "Start Conversation";
        startButton.classList.remove('recording');
      }
    };
  });
}

// Send event to WebSocket
function sendEvent(event) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(event));
    event.timestamp = Date.now();
    console.log("Sent event:", event);
  } else {
    console.warn("Cannot send event: WebSocket not connected");
  }
}

// Handle incoming message from WebSocket
function handleIncomingMessage(message) {
  console.log("Received event:", message);
  
  const eventType = Object.keys(message?.event)[0];
  
  if (!eventType) return;
  
  switch (eventType) {
    case "textOutput":
      const role = message.event[eventType].role;
      const content = message.event[eventType].content;
      const contentId = message.event[eventType].contentId;
      
      // Detect interruption
      if (role === "ASSISTANT" && content.startsWith("{")) {
        try {
          const evt = JSON.parse(content);
          if (evt.interrupted === true) {
            audioPlayer.bargeIn();
          }
        } catch (e) {
          // Not a JSON object, ignore
        }
      }
      
      // Update chat messages
      if (chatMessages.hasOwnProperty(contentId)) {
        chatMessages[contentId].content = content;
        chatMessages[contentId].role = role;
      }
      
      updateConversation();
      break;
      
    case "audioOutput":
      try {
        const base64Data = message.event[eventType].content;
        const audioData = base64ToFloat32Array(base64Data);
        audioPlayer.playAudio(audioData);
        updateStatus("Playing audio...", "playing");
      } catch (error) {
        console.error("Error processing audio chunk:", error);
      }
      break;
      
    case "contentStart":
      const contentType = message.event[eventType].type;
      const contentRole = message.event[eventType].role;
      const newContentId = message.event[eventType].contentId;
      
      if (contentType === "TEXT") {
        chatMessages[newContentId] = {
          "content": "",
          "role": contentRole
        };
        updateConversation();
      }
      break;
      
    default:
      break;
  }
}

// Start microphone recording
async function startMicrophone() {
  try {
    console.log("Requesting microphone access...");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
    console.log("Microphone access granted");
    
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      latencyHint: 'interactive'
    });
    
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(512, 1, 1);
    
    source.connect(processor);
    processor.connect(audioContext.destination);
    
    const targetSampleRate = 16000;
    
    processor.onaudioprocess = async (e) => {
      const startButton = document.getElementById('startButton');
      if (startButton && startButton.textContent === "End Conversation") {
        const inputBuffer = e.inputBuffer;
        
        // Create an offline context for resampling
        const offlineContext = new OfflineAudioContext({
          numberOfChannels: 1,
          length: Math.ceil(inputBuffer.duration * targetSampleRate),
          sampleRate: targetSampleRate
        });
        
        // Copy input to offline context buffer
        const offlineSource = offlineContext.createBufferSource();
        const monoBuffer = offlineContext.createBuffer(1, inputBuffer.length, inputBuffer.sampleRate);
        monoBuffer.copyToChannel(inputBuffer.getChannelData(0), 0);
        
        offlineSource.buffer = monoBuffer;
        offlineSource.connect(offlineContext.destination);
        offlineSource.start(0);
        
        // Resample and get the rendered buffer
        const renderedBuffer = await offlineContext.startRendering();
        const resampled = renderedBuffer.getChannelData(0);
        
        // Convert to Int16 PCM
        const buffer = new ArrayBuffer(resampled.length * 2);
        const pcmData = new DataView(buffer);
        
        for (let i = 0; i < resampled.length; i++) {
          const s = Math.max(-1, Math.min(1, resampled[i]));
          pcmData.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        
        // Convert to binary string and base64 encode
        let binary = '';
        for (let i = 0; i < pcmData.byteLength; i++) {
          binary += String.fromCharCode(pcmData.getUint8(i));
        }
        
        const base64Data = btoa(binary);
        
        // Send audio data
        const event = S2sEvent.audioInput(
          promptName,
          audioContentName,
          base64Data
        );
        sendEvent(event);
      }
    };
    
    // Cleanup function
    window.audioCleanup = () => {
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach(track => track.stop());
    };
    
    console.log('Microphone recording started');
    
  } catch (error) {
    console.error('Error accessing microphone:', error);
    throw error;
  }
}

// End the session
function endSession() {
  console.log("Ending session...");
  if (socket && socket.readyState === WebSocket.OPEN) {
    // Close microphone
    if (window.audioCleanup) {
      window.audioCleanup();
      console.log("Microphone recording stopped");
    }
    
    // Close session
    sendEvent(S2sEvent.contentEnd(promptName, audioContentName));
    sendEvent(S2sEvent.promptEnd(promptName));
    sendEvent(S2sEvent.sessionEnd());
    
    // Close WebSocket
    socket.close();
    console.log("WebSocket closed");
  }
}

// Update the conversation display
function updateConversation() {
  const conversationElement = document.getElementById('conversation');
  
  let html = '';
  
  Object.keys(chatMessages).forEach(key => {
    const message = chatMessages[key];
    if (message.content) {
      const messageClass = message.role === 'USER' ? 'user' : 'assistant';
      html += `<div class="message ${messageClass}">${message.content}</div>`;
    }
  });
  
  conversationElement.innerHTML = html;
  
  // Scroll to bottom
  conversationElement.scrollTop = conversationElement.scrollHeight;
}

// Update status display
function updateStatus(message, className = '') {
  const statusElement = document.getElementById('status');
  if (statusElement) {
    statusElement.textContent = message;
    statusElement.className = 'status ' + className;
  }
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', initApp);

// Initialize immediately if the document is already loaded
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  initApp();
}
