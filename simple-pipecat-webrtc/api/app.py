import asyncio
import json
import logging
import os
import uuid
import base64
from typing import Dict, Optional, List, Any

import aiortc
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# AWS SDK imports
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver

# Import audio utilities
from audio_utils import convert_audio_for_nova_sonic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure AWS credentials
os.environ["AWS_PROFILE"] = os.getenv("AWS_PROFILE", "ml-sandbox")
os.environ["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")

# Create FastAPI app
app = FastAPI(title="WebRTC Audio API with Amazon Nova Sonic")

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

# Store active Nova Sonic sessions
nova_sonic_sessions: Dict[str, Any] = {}

# Models
class WebRTCOffer(BaseModel):
    sdp: str
    type: str
    pc_id: Optional[str] = None

class SimpleNovaSonic:
    """
    A class to handle Nova Sonic bidirectional streaming conversations.
    This implementation is based on the reference implementation from Amazon.
    """
    def __init__(self, model_id='amazon.nova-sonic-v1:0', region='us-east-1', voice_id='Lisa'):
        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.client = None
        self.stream = None
        self.response = None
        self.is_active = False
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self.audio_queue = asyncio.Queue()
        self.role = None
        self.display_assistant_text = False
        self.max_tokens = 1024
        self.temperature = 0.7
        self.top_p = 0.9
        self.input_sample_rate = 16000
        self.output_sample_rate = 24000
        
    def _initialize_client(self):
        """Initialize the Bedrock client."""
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()}
        )
        self.client = BedrockRuntimeClient(config=config)
        logger.info(f"Initialized Nova Sonic client in region {self.region}")
    
    async def send_event(self, event_json):
        """Send an event to the stream."""
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        await self.stream.input_stream.send(event)
        logger.debug(f"Sent event: {event_json[:100]}...")
    
    async def start_session(self):
        """Start a new session with Nova Sonic."""
        if not self.client:
            self._initialize_client()
            
        # Initialize the stream
        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True
        logger.info("Started Nova Sonic session")
        
        # Send session start event
        session_start = f'''
        {{
          "event": {{
            "sessionStart": {{
              "inferenceConfiguration": {{
                "maxTokens": {self.max_tokens},
                "topP": {self.top_p},
                "temperature": {self.temperature}
              }}
            }}
          }}
        }}
        '''
        await self.send_event(session_start)
        
        # Send prompt start event
        prompt_start = f'''
        {{
          "event": {{
            "promptStart": {{
              "promptName": "{self.prompt_name}",
              "textOutputConfiguration": {{
                "mediaType": "text/plain"
              }},
              "audioOutputConfiguration": {{
                "mediaType": "audio/lpcm",
                "sampleRateHertz": {self.output_sample_rate},
                "sampleSizeBits": 16,
                "channelCount": 1,
                "voiceId": "{self.voice_id}",
                "encoding": "base64",
                "audioType": "SPEECH"
              }}
            }}
          }}
        }}
        '''
        await self.send_event(prompt_start)
        
        # Send system prompt
        text_content_start = f'''
        {{
            "event": {{
                "contentStart": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.content_name}",
                    "type": "TEXT",
                    "interactive": true,
                    "role": "SYSTEM",
                    "textInputConfiguration": {{
                        "mediaType": "text/plain"
                    }}
                }}
            }}
        }}
        '''
        await self.send_event(text_content_start)
        
        system_prompt = "You are a friendly assistant. The user and you will engage in a spoken dialog " \
            "exchanging the transcripts of a natural real-time conversation. Keep your responses short, " \
            "generally two or three sentences for chatty scenarios."
        
        text_input = f'''
        {{
            "event": {{
                "textInput": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.content_name}",
                    "content": "{system_prompt}"
                }}
            }}
        }}
        '''
        await self.send_event(text_input)
        
        text_content_end = f'''
        {{
            "event": {{
                "contentEnd": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.content_name}"
                }}
            }}
        }}
        '''
        await self.send_event(text_content_end)
        
        # Start processing responses
        self.response = asyncio.create_task(self._process_responses())
        logger.info("Nova Sonic session fully initialized and ready for conversation")
    
    async def start_audio_input(self):
        """Start audio input stream."""
        # Generate a new unique content name for each audio input
        self.audio_content_name = str(uuid.uuid4())
        logger.debug(f"Generated new audio content name: {self.audio_content_name}")
        
        audio_content_start = f'''
        {{
            "event": {{
                "contentStart": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.audio_content_name}",
                    "type": "AUDIO",
                    "interactive": true,
                    "role": "USER",
                    "audioInputConfiguration": {{
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": {self.input_sample_rate},
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64"
                    }}
                }}
            }}
        }}
        '''
        await self.send_event(audio_content_start)
        logger.info("Started audio input stream")
    
    async def send_audio_chunk(self, audio_bytes):
        """Send an audio chunk to the stream."""
        if not self.is_active:
            logger.warning("Attempted to send audio chunk but session is not active")
            return
            
        blob = base64.b64encode(audio_bytes)
        audio_event = f'''
        {{
            "event": {{
                "audioInput": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.audio_content_name}",
                    "content": "{blob.decode('utf-8')}"
                }}
            }}
        }}
        '''
        await self.send_event(audio_event)
    
    async def end_audio_input(self):
        """End audio input stream."""
        audio_content_end = f'''
        {{
            "event": {{
                "contentEnd": {{
                    "promptName": "{self.prompt_name}",
                    "contentName": "{self.audio_content_name}"
                }}
            }}
        }}
        '''
        await self.send_event(audio_content_end)
        logger.info("Ended audio input stream")
    
    async def end_session(self):
        """End the session."""
        if not self.is_active:
            logger.warning("Attempted to end session but session is not active")
            return
            
        prompt_end = f'''
        {{
            "event": {{
                "promptEnd": {{
                    "promptName": "{self.prompt_name}"
                }}
            }}
        }}
        '''
        await self.send_event(prompt_end)
        
        session_end = '''
        {
            "event": {
                "sessionEnd": {}
            }
        }
        '''
        await self.send_event(session_end)
        
        # Close the stream
        await self.stream.input_stream.close()
        self.is_active = False
        
        # Cancel the response task if it's still running
        if self.response and not self.response.done():
            self.response.cancel()
            
        logger.info("Ended Nova Sonic session")
    
    async def _process_responses(self):
        """Process responses from the stream."""
        try:
            text_response = ""
            audio_chunks = []
            
            while self.is_active:
                output = await self.stream.await_output()
                result = await output[1].receive()
                
                if result.value and result.value.bytes_:
                    response_data = result.value.bytes_.decode('utf-8')
                    json_data = json.loads(response_data)
                    
                    if 'event' in json_data:
                        # Handle content start event
                        if 'contentStart' in json_data['event']:
                            content_start = json_data['event']['contentStart'] 
                            # Set role
                            self.role = content_start.get('role')
                            logger.debug(f"Content start with role: {self.role}")
                            
                            # Check for speculative content
                            if 'additionalModelFields' in content_start:
                                additional_fields = json.loads(content_start['additionalModelFields'])
                                if additional_fields.get('generationStage') == 'SPECULATIVE':
                                    self.display_assistant_text = True
                                else:
                                    self.display_assistant_text = False
                                    
                        # Handle text output event
                        elif 'textOutput' in json_data['event']:
                            text = json_data['event']['textOutput']['content']
                            text_response += text
                            
                            if (self.role == "ASSISTANT" and self.display_assistant_text):
                                logger.info(f"Assistant text: {text}")
                            elif self.role == "USER":
                                logger.info(f"User text: {text}")
                        
                        # Handle audio output
                        elif 'audioOutput' in json_data['event']:
                            audio_content = json_data['event']['audioOutput']['content']
                            audio_bytes = base64.b64decode(audio_content)
                            audio_chunks.append(audio_bytes)
                            await self.audio_queue.put(audio_bytes)
                            logger.debug(f"Received audio chunk: {len(audio_bytes)} bytes")
                            
                        # Handle completion end
                        elif 'completionEnd' in json_data['event']:
                            logger.info("Received completion end event")
                            
            return text_response, audio_chunks
                            
        except asyncio.CancelledError:
            logger.info("Response processing task was cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error processing responses: {e}")
            return "", []

@app.get("/")
async def root():
    return {"message": "WebRTC Audio API with Amazon Nova Sonic is running"}

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
                # Clean up Nova Sonic session if it exists
                if pc_id in nova_sonic_sessions:
                    nova_sonic = nova_sonic_sessions[pc_id]
                    if nova_sonic.is_active:
                        await nova_sonic.end_session()
                    del nova_sonic_sessions[pc_id]
                
                # Remove peer connection
                if pc_id in peer_connections:
                    del peer_connections[pc_id]
        
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"Data channel established: {channel.label}")
            
            # Initialize Nova Sonic session for this connection
            try:
                # Create Nova Sonic instance
                nova_sonic = SimpleNovaSonic(
                    model_id=os.getenv("NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0"),
                    region=os.environ["AWS_REGION"],
                    voice_id=os.getenv("NOVA_SONIC_VOICE_ID", "Lisa")
                )
                
                # Store the session
                nova_sonic_sessions[pc_id] = nova_sonic
                
                # Flag to track if we're currently receiving audio
                receiving_audio = False
                audio_chunks = []
                audio_metadata = {}
                
                logger.info(f"Nova Sonic session initialized for connection {pc_id}")
            except Exception as e:
                logger.error(f"Failed to initialize Nova Sonic session: {e}")
                # Continue anyway, we'll handle the error when processing audio
            
            @channel.on("message")
            async def on_message(message):
                nonlocal receiving_audio, audio_chunks, audio_metadata
                
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
                            
                            # Acknowledge the start message
                            channel.send(json.dumps({
                                'type': 'audio-start-ack',
                                'label': 'nova-sonic',
                                'data': {
                                    'status': 'receiving'
                                }
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
                            
                            logger.debug(f"Received audio chunk {chunk_index + 1}/{chunk_data.get('totalChunks', '?')} "
                                      f"({len(chunk_bytes)} bytes)")
                            
                        elif msg_type == 'audio-end' and receiving_audio:
                            # Finished receiving audio
                            logger.info(f"Finished receiving audio, processing with Nova Sonic ({len(audio_chunks)} chunks)")
                            receiving_audio = False
                            
                            # Process the audio with Nova Sonic
                            asyncio.create_task(process_audio_with_nova_sonic(audio_chunks, audio_metadata))
                            
                            # Clear audio data
                            audio_chunks = []
                            audio_metadata = {}
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Received non-JSON message: {message[:50]}...")
                else:
                    logger.info(f"Received binary message: {len(message)} bytes")
            
            async def process_audio_with_nova_sonic(audio_chunks, metadata):
                """Process audio with Nova Sonic and stream the response back"""
                try:
                    # Get Nova Sonic instance
                    nova_sonic = nova_sonic_sessions.get(pc_id)
                    if not nova_sonic:
                        logger.error(f"No Nova Sonic session found for connection {pc_id}")
                        return
                    
                    # Convert audio to the format required by Nova Sonic
                    try:
                        nova_sonic_audio = convert_audio_for_nova_sonic(audio_chunks, metadata)
                        logger.info(f"Converted audio for Nova Sonic: {len(nova_sonic_audio)} bytes")
                    except Exception as e:
                        logger.error(f"Error converting audio: {e}")
                        channel.send(json.dumps({
                            'type': 'error',
                            'label': 'nova-sonic',
                            'data': {
                                'message': f"Error converting audio: {str(e)}"
                            }
                        }))
                        return
                    
                    # Start Nova Sonic session if not already started
                    if not nova_sonic.is_active:
                        await nova_sonic.start_session()
                    
                    # Start audio input with a new unique content name
                    await nova_sonic.start_audio_input()
                    
                    # Send audio data
                    await nova_sonic.send_audio_chunk(nova_sonic_audio)
                    
                    # End audio input
                    await nova_sonic.end_audio_input()
                    
                    # Process responses
                    text_response = ""
                    audio_response = []
                    
                    # Wait for audio to be available in the queue
                    while True:
                        try:
                            audio_bytes = await asyncio.wait_for(nova_sonic.audio_queue.get(), timeout=0.5)
                            audio_response.append(audio_bytes)
                            
                            # Check if we have more audio in the queue
                            if nova_sonic.audio_queue.empty():
                                # Wait a bit more to see if more audio arrives
                                await asyncio.sleep(0.5)
                                if nova_sonic.audio_queue.empty():
                                    break
                        except asyncio.TimeoutError:
                            # No more audio available
                            break
                    
                    # Combine all audio chunks
                    full_audio = b''.join(audio_response)
                    logger.info(f"Total audio received from Nova Sonic: {len(full_audio)} bytes")
                    
                    # Calculate number of chunks to send back to client
                    chunk_size = 1024  # Use a reasonable chunk size for WebRTC
                    total_chunks = (len(full_audio) + chunk_size - 1) // chunk_size
                    
                    # Send start message
                    channel.send(json.dumps({
                        'type': 'audio-start',
                        'label': 'nova-sonic',
                        'data': {
                            'filename': 'nova-sonic-response.wav',
                            'mimeType': 'audio/wav',
                            'totalChunks': total_chunks,
                            'text': text_response  # Include the text response
                        }
                    }))
                    
                    # Stream the audio back in chunks
                    for i in range(total_chunks):
                        # Get chunk of audio
                        start_idx = i * chunk_size
                        end_idx = min(start_idx + chunk_size, len(full_audio))
                        chunk = full_audio[start_idx:end_idx]
                        
                        # Convert to list for JSON serialization
                        chunk_array = list(chunk)
                        
                        channel.send(json.dumps({
                            'type': 'audio-chunk',
                            'label': 'nova-sonic',
                            'data': {
                                'chunkIndex': i,
                                'totalChunks': total_chunks,
                                'chunk': chunk_array
                            }
                        }))
                        logger.debug(f"Sent Nova Sonic audio chunk {i + 1}/{total_chunks}")
                        
                        # Add a small delay to simulate streaming
                        await asyncio.sleep(0.05)
                    
                    # Send end message
                    channel.send(json.dumps({
                        'type': 'audio-end',
                        'label': 'nova-sonic',
                        'data': {
                            'filename': 'nova-sonic-response.wav'
                        }
                    }))
                    logger.info("Finished sending Nova Sonic audio response")
                    
                except Exception as e:
                    logger.exception(f"Error processing audio with Nova Sonic: {e}")
                    # Send error message to client
                    channel.send(json.dumps({
                        'type': 'error',
                        'label': 'nova-sonic',
                        'data': {
                            'message': f"Error processing audio: {str(e)}"
                        }
                    }))
        
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
    Close all peer connections and Nova Sonic sessions on shutdown
    """
    # End all Nova Sonic sessions
    for nova_sonic in nova_sonic_sessions.values():
        if nova_sonic.is_active:
            await nova_sonic.end_session()
    
    # Close peer connections
    coros = [pc.close() for pc in peer_connections.values()]
    await asyncio.gather(*coros)
    
    # Clear dictionaries
    peer_connections.clear()
    nova_sonic_sessions.clear()
    
    logger.info("All connections and sessions closed")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting WebRTC Audio API with Amazon Nova Sonic integration on {host}:{port}")
    logger.info(f"Using AWS Profile: {os.environ['AWS_PROFILE']}, Region: {os.environ['AWS_REGION']}")
    uvicorn.run("app:app", host=host, port=port, reload=debug)