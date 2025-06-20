import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Optional

import aiortc
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webrtc-api")

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(title="WebRTC Audio API - Simple Test")

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active peer connections
peer_connections: Dict[str, RTCPeerConnection] = {}

# Models
class WebRTCOffer(BaseModel):
    sdp: str
    type: str
    pc_id: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "WebRTC Audio API Test Server is running"}

@app.post("/offer")
async def process_offer(request: Request):
    """
    Process WebRTC offer from client and return answer
    """
    try:
        # Parse request body
        body = await request.json()
        offer_data = WebRTCOffer(**body)
        
        logger.info(f"Received offer: type={offer_data.type}, pc_id={offer_data.pc_id}")
        
        # Create a new peer connection
        pc = RTCPeerConnection()
        pc_id = offer_data.pc_id or str(uuid.uuid4())
        
        # Store the peer connection
        peer_connections[pc_id] = pc
        
        # Set up event handlers
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state changed to: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                if pc_id in peer_connections:
                    del peer_connections[pc_id]
        
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"Data channel established: {channel.label}")
            
            # Store audio chunks for each connection
            audio_chunks = []
            audio_metadata = {}
            receiving_audio = False
            
            @channel.on("message")
            def on_message(message):
                nonlocal audio_chunks, audio_metadata, receiving_audio
                
                if isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type', 'unknown')
                        logger.info(f"Received message: {msg_type}")
                        
                        # Handle different message types
                        if msg_type == 'audio-start':
                            # Start receiving audio
                            receiving_audio = True
                            audio_chunks = []
                            audio_metadata = data.get('data', {})
                            logger.info(f"Started receiving audio: {audio_metadata.get('filename', 'unknown')} "
                                       f"({audio_metadata.get('fileSize', 0)} bytes)")
                            
                            # Echo back the start message
                            channel.send(json.dumps({
                                'type': 'audio-start',
                                'label': 'server-echo',
                                'data': audio_metadata
                            }))
                            
                        elif msg_type == 'audio-chunk' and receiving_audio:
                            # Store audio chunk
                            chunk_data = data.get('data', {})
                            chunk_index = chunk_data.get('chunkIndex', -1)
                            chunk_array = chunk_data.get('chunk', [])
                            
                            # Convert array back to bytes
                            chunk_bytes = bytes(chunk_array)
                            
                            # Store chunk at the correct index
                            while len(audio_chunks) <= chunk_index:
                                audio_chunks.append(None)
                            audio_chunks[chunk_index] = chunk_bytes
                            
                            logger.info(f"Received audio chunk {chunk_index + 1}/{chunk_data.get('totalChunks', '?')} "
                                       f"({len(chunk_bytes)} bytes)")
                            
                        elif msg_type == 'audio-end' and receiving_audio:
                            # Finished receiving audio
                            logger.info(f"Finished receiving audio, echoing back {len(audio_chunks)} chunks")
                            receiving_audio = False
                            
                            # Echo back all chunks
                            total_chunks = len(audio_chunks)
                            
                            # Send start message
                            channel.send(json.dumps({
                                'type': 'audio-start',
                                'label': 'server-echo',
                                'data': {
                                    'filename': audio_metadata.get('filename', 'echo.wav'),
                                    'fileSize': sum(len(chunk) for chunk in audio_chunks if chunk is not None),
                                    'mimeType': audio_metadata.get('mimeType', 'audio/wav'),
                                    'totalChunks': total_chunks
                                }
                            }))
                            
                            # Send each chunk
                            for i, chunk in enumerate(audio_chunks):
                                if chunk is not None:
                                    # Convert bytes to array for JSON serialization
                                    chunk_array = list(chunk)
                                    
                                    channel.send(json.dumps({
                                        'type': 'audio-chunk',
                                        'label': 'server-echo',
                                        'data': {
                                            'chunkIndex': i,
                                            'totalChunks': total_chunks,
                                            'chunk': chunk_array
                                        }
                                    }))
                                    logger.info(f"Sent echo chunk {i + 1}/{total_chunks} ({len(chunk)} bytes)")
                            
                            # Send end message
                            channel.send(json.dumps({
                                'type': 'audio-end',
                                'label': 'server-echo',
                                'data': {
                                    'filename': audio_metadata.get('filename', 'echo.wav')
                                }
                            }))
                            logger.info("Finished sending echo audio")
                            
                            # Clear audio data
                            audio_chunks = []
                            audio_metadata = {}
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Received non-JSON message: {message[:50]}...")
                else:
                    logger.info(f"Received binary message: {len(message)} bytes")
        
        # Create media sink
        player = MediaBlackhole()
        
        # Set remote description
        offer = RTCSessionDescription(sdp=offer_data.sdp, type=offer_data.type)
        await pc.setRemoteDescription(offer)
        
        # Add media
        for t in pc.getTransceivers():
            if t.kind == "audio" and player.audio:
                pc.addTrack(player.audio)
        
        # Create answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Wait for ICE gathering to complete
        await asyncio.sleep(1)  # Give some time for ICE gathering
        
        logger.info(f"Created answer: type={pc.localDescription.type}")
        logger.info(f"ICE gathering state: {pc.iceGatheringState}")
        
        # Return the answer
        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "pc_id": pc_id
        }
    
    except Exception as e:
        logger.error(f"Error processing offer: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("shutdown")
async def on_shutdown():
    """
    Close all peer connections on shutdown
    """
    coros = [pc.close() for pc in peer_connections.values()]
    await asyncio.gather(*coros)
    peer_connections.clear()

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting WebRTC Audio API on {host}:{port}")
    uvicorn.run("app_simple:app", host=host, port=port, reload=debug)