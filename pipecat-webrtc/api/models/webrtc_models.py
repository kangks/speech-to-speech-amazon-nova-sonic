from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class WebRTCOffer(BaseModel):
    """
    Model for WebRTC offer from client
    """
    sdp: str = Field(..., description="Session Description Protocol string")
    type: str = Field(..., description="SDP type (offer)")
    pc_id: Optional[str] = Field(None, description="Peer connection ID for reconnection")
    restart_pc: Optional[bool] = Field(False, description="Whether to restart the peer connection")


class WebRTCAnswer(BaseModel):
    """
    Model for WebRTC answer from server
    """
    sdp: str = Field(..., description="Session Description Protocol string")
    type: str = Field(..., description="SDP type (answer)")
    pc_id: str = Field(..., description="Peer connection ID for future reference")


class AudioStartMessage(BaseModel):
    """
    Model for audio start message
    """
    filename: str = Field(..., description="Filename of the audio")
    fileSize: int = Field(..., description="Size of the audio file in bytes")
    mimeType: str = Field(..., description="MIME type of the audio file")
    totalChunks: int = Field(..., description="Total number of chunks")


class AudioChunkMessage(BaseModel):
    """
    Model for audio chunk message
    """
    chunkIndex: int = Field(..., description="Index of the chunk")
    totalChunks: int = Field(..., description="Total number of chunks")
    chunk: List[int] = Field(..., description="Audio chunk data as byte array")


class AudioEndMessage(BaseModel):
    """
    Model for audio end message
    """
    filename: str = Field(..., description="Filename of the audio")


class DataChannelMessage(BaseModel):
    """
    Model for data channel message
    """
    type: str = Field(..., description="Message type (audio-start, audio-chunk, audio-end, client-ready)")
    label: str = Field(..., description="Message label")
    data: Dict[str, Any] = Field(default_factory=dict, description="Message data")