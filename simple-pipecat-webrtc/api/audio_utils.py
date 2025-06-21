"""
Utility functions for audio processing and format conversion between WebRTC and Nova Sonic.
"""

import io
import logging
import numpy as np
import wave
from typing import Tuple, List, Optional

logger = logging.getLogger("audio-utils")

def wav_to_pcm(wav_bytes: bytes) -> Tuple[bytes, int, int]:
    """
    Convert WAV bytes to PCM bytes.
    
    Args:
        wav_bytes: WAV file bytes
        
    Returns:
        Tuple of (PCM bytes, sample rate, number of channels)
    """
    try:
        with io.BytesIO(wav_bytes) as wav_buffer:
            with wave.open(wav_buffer, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                num_frames = wav_file.getnframes()
                
                # Read all frames
                pcm_data = wav_file.readframes(num_frames)
                
                logger.debug(f"Converted WAV to PCM: {len(pcm_data)} bytes, "
                           f"{sample_rate} Hz, {num_channels} channels, "
                           f"{sample_width} bytes per sample")
                
                return pcm_data, sample_rate, num_channels
    except Exception as e:
        logger.error(f"Error converting WAV to PCM: {e}")
        raise

def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, num_channels: int = 1, 
               sample_width: int = 2) -> bytes:
    """
    Convert PCM bytes to WAV bytes.
    
    Args:
        pcm_bytes: PCM audio bytes
        sample_rate: Sample rate in Hz (default: 16000)
        num_channels: Number of channels (default: 1 for mono)
        sample_width: Sample width in bytes (default: 2 for 16-bit)
        
    Returns:
        WAV file bytes
    """
    try:
        with io.BytesIO() as wav_buffer:
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(num_channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_bytes)
            
            wav_bytes = wav_buffer.getvalue()
            logger.debug(f"Converted PCM to WAV: {len(wav_bytes)} bytes")
            return wav_bytes
    except Exception as e:
        logger.error(f"Error converting PCM to WAV: {e}")
        raise

def resample_audio(audio_data: bytes, original_rate: int, target_rate: int = 16000,
                  num_channels: int = 1, sample_width: int = 2) -> bytes:
    """
    Resample audio to the target sample rate.
    
    Args:
        audio_data: Audio data as bytes
        original_rate: Original sample rate in Hz
        target_rate: Target sample rate in Hz (default: 16000)
        num_channels: Number of channels (default: 1 for mono)
        sample_width: Sample width in bytes (default: 2 for 16-bit)
        
    Returns:
        Resampled audio data as bytes
    """
    try:
        if original_rate == target_rate:
            return audio_data
        
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Reshape for multi-channel if needed
        if num_channels > 1:
            audio_array = audio_array.reshape(-1, num_channels)
        
        # Calculate resampling ratio
        ratio = target_rate / original_rate
        
        # Calculate new length
        new_length = int(len(audio_array) * ratio)
        
        # Resample using numpy
        indices = np.arange(0, len(audio_array), 1/ratio)[:new_length]
        indices = indices.astype(np.int32)
        
        # Handle multi-channel audio
        if num_channels > 1:
            resampled = np.zeros((new_length, num_channels), dtype=np.int16)
            for i in range(num_channels):
                resampled[:, i] = audio_array[indices, i]
        else:
            resampled = audio_array[indices]
        
        # Convert back to bytes
        resampled_bytes = resampled.tobytes()
        
        logger.debug(f"Resampled audio from {original_rate}Hz to {target_rate}Hz: "
                   f"{len(audio_data)} bytes -> {len(resampled_bytes)} bytes")
        
        return resampled_bytes
    except Exception as e:
        logger.error(f"Error resampling audio: {e}")
        raise

def convert_audio_for_nova_sonic(audio_chunks: List[bytes], 
                                metadata: dict) -> bytes:
    """
    Convert audio chunks to the format required by Nova Sonic.
    
    Args:
        audio_chunks: List of audio chunk bytes
        metadata: Audio metadata dictionary
        
    Returns:
        Audio bytes in the format required by Nova Sonic
    """
    try:
        # Combine all chunks
        combined_audio = bytearray()
        for chunk in audio_chunks:
            if chunk is not None:
                combined_audio.extend(chunk)
        
        # Get audio format information from metadata
        mime_type = metadata.get('mimeType', 'audio/wav')
        
        # Process based on mime type
        if mime_type == 'audio/wav':
            # Already WAV, extract PCM and ensure correct format
            pcm_data, sample_rate, num_channels = wav_to_pcm(combined_audio)
            
            # Resample if needed (Nova Sonic expects 16kHz)
            if sample_rate != 16000:
                pcm_data = resample_audio(pcm_data, sample_rate, 16000, num_channels)
            
            # Convert to mono if needed
            if num_channels > 1:
                # Simple conversion by taking average of channels
                # In a real implementation, you might want a more sophisticated approach
                audio_array = np.frombuffer(pcm_data, dtype=np.int16).reshape(-1, num_channels)
                mono_array = np.mean(audio_array, axis=1).astype(np.int16)
                pcm_data = mono_array.tobytes()
            
            # Convert back to WAV for Nova Sonic
            return pcm_to_wav(pcm_data, 16000, 1)
        else:
            # For other formats, you would need to implement appropriate conversion
            # This is a simplified implementation
            logger.warning(f"Unsupported audio format: {mime_type}, attempting to process as raw PCM")
            return pcm_to_wav(combined_audio, 16000, 1)
    except Exception as e:
        logger.error(f"Error converting audio for Nova Sonic: {e}")
        raise