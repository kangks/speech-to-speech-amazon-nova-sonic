# Nova Sonic Vite Client

A minimal Vite web client that replicates the functionality of the Nova Sonic React client. This implementation focuses on core functionality with minimal dependencies.

## Features

- Audio recording from the microphone using Web Audio API
- WebSocket connection management for communication with the Nova Sonic backend
- Audio playback using AudioWorklet API
- Transcript display for conversation history
- Basic UI components for interaction

## Prerequisites

- Node.js (v16 or later)
- A running Nova Sonic backend server

## Setup

1. Install dependencies:

```bash
npm install
```

2. Configure the WebSocket URL:

Create a `.env` file in the project root with the following content:

```
VITE_WEBSOCKET_URL=ws://localhost:8081
```

Replace the URL with your Nova Sonic backend server address if different.

## Development

To run the development server:

```bash
npm run dev
```

This will start the Vite development server, typically at http://localhost:5173.

## Build

To build the application for production:

```bash
npm run build
```

The built files will be in the `dist` directory.

## Preview

To preview the production build:

```bash
npm run preview
```

## Implementation Details

### Audio Recording

- Uses the Web Audio API to capture audio from the microphone
- Applies noise suppression and echo cancellation
- Resamples to 16kHz and converts to Int16 PCM format
- Base64 encodes the audio data for transmission

### WebSocket Connection

- Establishes and maintains a WebSocket connection to the backend
- Implements the session protocol (sessionStart, promptStart, etc.)
- Handles incoming events from the backend

### Audio Playback

- Uses AudioWorklet API for efficient audio processing
- Implements a custom AudioWorkletProcessor for audio buffering
- Handles base64-encoded audio from backend and converts to Float32Array
- Supports barge-in functionality to interrupt playback

### Transcript Display

- Processes incoming text events
- Displays conversation history with appropriate styling for user and assistant messages

## Project Structure

- `src/main.js` - Main application logic
- `src/helper/audioHelper.js` - Audio conversion utilities
- `src/helper/audioPlayer.js` - Audio playback implementation
- `src/helper/audioPlayerProcessor.worklet.js` - AudioWorklet implementation
- `src/helper/s2sEvents.js` - WebSocket event handling
- `src/style.css` - Application styling