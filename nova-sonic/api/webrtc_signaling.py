import asyncio
import json
import logging
import uuid
from typing import Dict, Optional, Callable, Any, List

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from fastapi import WebSocket

from models.webrtc_models import WebRTCOffer, WebRTCAnswer

# Configure logging
logger = logging.getLogger("webrtc-signaling")


class WebRTCSignalingManager:
    """
    Manager for WebRTC signaling and data channel communication
    """
    def __init__(self):
        # Store active peer connections
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        # Store data channel message handlers
        self.message_handlers: Dict[str, Callable] = {}

    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """
        Register a handler for a specific message type
        """
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")

    async def process_offer(self, offer_data: WebRTCOffer) -> WebRTCAnswer:
        """
        Process WebRTC offer from client and return answer
        """
        try:
            logger.info(f"Received offer: type={offer_data.type}, pc_id={offer_data.pc_id}")
            
            # Check if we need to reuse an existing connection
            if offer_data.pc_id and offer_data.pc_id in self.peer_connections:
                # Reuse existing connection
                pc = self.peer_connections[offer_data.pc_id]
                pc_id = offer_data.pc_id
                logger.info(f"Reusing existing connection for pc_id: {pc_id}")
                
                # If restart_pc is True, close and recreate the connection
                if offer_data.restart_pc:
                    await pc.close()
                    pc = RTCPeerConnection()
                    self.peer_connections[pc_id] = pc
                    logger.info(f"Restarted peer connection for pc_id: {pc_id}")
                    
                    # Set up event handlers for the new connection
                    self._setup_event_handlers(pc, pc_id)
            else:
                # Create a new peer connection
                pc = RTCPeerConnection()
                pc_id = offer_data.pc_id or str(uuid.uuid4())
                
                # Store the peer connection
                self.peer_connections[pc_id] = pc
                
                # Set up event handlers
                self._setup_event_handlers(pc, pc_id)
            
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
            return WebRTCAnswer(
                sdp=pc.localDescription.sdp,
                type=pc.localDescription.type,
                pc_id=pc_id
            )
        
        except Exception as e:
            logger.error(f"Error processing offer: {e}", exc_info=True)
            raise

    def _setup_event_handlers(self, pc: RTCPeerConnection, pc_id: str) -> None:
        """
        Set up event handlers for a peer connection
        """
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state changed to: {pc.connectionState}")
            if pc.connectionState == "failed" or pc.connectionState == "closed":
                if pc_id in self.peer_connections:
                    del self.peer_connections[pc_id]
        
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
                        
                        # Check if we have a registered handler for this message type
                        if msg_type in self.message_handlers:
                            # Call the registered handler
                            self.message_handlers[msg_type](data, channel)
                            return
                        
                        # Default handlers for audio messages
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

    async def close_all_connections(self) -> None:
        """
        Close all peer connections
        """
        coros = [pc.close() for pc in self.peer_connections.values()]
        await asyncio.gather(*coros)
        self.peer_connections.clear()
        logger.info("Closed all peer connections")