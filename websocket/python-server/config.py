import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Centralized configuration management for the Nova Sonic Python server."""
    
    # Server configuration
    HOST = os.getenv("HOST", "0.0.0.0")  # Default to 0.0.0.0 for containerization
    WS_PORT = int(os.getenv("WS_PORT", "8000"))
    HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080")) if os.getenv("HEALTH_PORT") else None
    
    # Debug and logging
    LOGLEVEL = os.getenv("LOGLEVEL", "INFO").upper()
    LOG_FILE = os.getenv("LOG_FILE", None)
    
    # AWS configuration
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_PROFILE = os.getenv("AWS_PROFILE")
    
    # Nova Sonic configuration
    NOVA_SONIC_MODEL_ID = os.getenv("NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0")
    
    # System prompt configuration
    DEFAULT_SYSTEM_PROMPT = os.getenv("DEFAULT_SYSTEM_PROMPT",
        "You are a friendly assistant. The user and you will engage in a spoken dialog "
        "exchanging the transcripts of a natural real-time conversation. Keep your responses short, "
        "generally two or three sentences for chatty scenarios.")
    
    # Inference configuration
    INFERENCE_MAX_TOKENS = int(os.getenv("INFERENCE_MAX_TOKENS", "1024"))
    INFERENCE_TOP_P = float(os.getenv("INFERENCE_TOP_P", "0.95"))
    INFERENCE_TEMPERATURE = float(os.getenv("INFERENCE_TEMPERATURE", "0.7"))
    
    # Audio input configuration
    AUDIO_INPUT_MEDIA_TYPE = os.getenv("AUDIO_INPUT_MEDIA_TYPE", "audio/lpcm")
    AUDIO_INPUT_SAMPLE_RATE = int(os.getenv("AUDIO_INPUT_SAMPLE_RATE", "16000"))
    AUDIO_INPUT_SAMPLE_SIZE = int(os.getenv("AUDIO_INPUT_SAMPLE_SIZE", "16"))
    AUDIO_INPUT_CHANNEL_COUNT = int(os.getenv("AUDIO_INPUT_CHANNEL_COUNT", "1"))
    AUDIO_INPUT_ENCODING = os.getenv("AUDIO_INPUT_ENCODING", "base64")
    
    # Audio output configuration
    AUDIO_OUTPUT_MEDIA_TYPE = os.getenv("AUDIO_OUTPUT_MEDIA_TYPE", "audio/lpcm")
    AUDIO_OUTPUT_SAMPLE_RATE = int(os.getenv("AUDIO_OUTPUT_SAMPLE_RATE", "24000"))
    AUDIO_OUTPUT_SAMPLE_SIZE = int(os.getenv("AUDIO_OUTPUT_SAMPLE_SIZE", "16"))
    AUDIO_OUTPUT_CHANNEL_COUNT = int(os.getenv("AUDIO_OUTPUT_CHANNEL_COUNT", "1"))
    AUDIO_OUTPUT_VOICE_ID = os.getenv("AUDIO_OUTPUT_VOICE_ID", "matthew")
    AUDIO_OUTPUT_ENCODING = os.getenv("AUDIO_OUTPUT_ENCODING", "base64")
    
    # Tool configuration
    ENABLE_TOOLS = os.getenv("ENABLE_TOOLS", "false").lower() == "true"
    
    # Agent configuration
    ENABLE_STRANDS_AGENT = os.getenv("ENABLE_STRANDS_AGENT", "false").lower() == "true"
    STRANDS_MODEL_ID = os.getenv("STRANDS_MODEL_ID", "amazon.nova-lite-v1:0")
    
    # MCP configuration
    FASTMCP_LOG_LEVEL = os.getenv("FASTMCP_LOG_LEVEL", "ERROR")
    
    @classmethod
    def configure_logging(cls):
        """Configure logging based on environment variables."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # Configure logging level
        logging.basicConfig(
            level=getattr(logging, cls.LOGLEVEL),
            format=log_format
        )
        
        # Add file handler if LOG_FILE is specified
        if cls.LOG_FILE:
            file_handler = logging.FileHandler(cls.LOG_FILE)
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
        
        # Suppress warnings
        import warnings
        warnings.filterwarnings("ignore")
    
    @classmethod
    def validate(cls):
        """Validate the configuration and return a list of errors."""
        errors = []
        
        # Check required AWS credentials
        if not cls.AWS_ACCESS_KEY_ID:
            errors.append("AWS_ACCESS_KEY_ID is not set")
        if not cls.AWS_SECRET_ACCESS_KEY:
            errors.append("AWS_SECRET_ACCESS_KEY is not set")
        
        # Validate inference configuration
        if cls.INFERENCE_MAX_TOKENS <= 0:
            errors.append("INFERENCE_MAX_TOKENS must be greater than 0")
        if not (0 < cls.INFERENCE_TOP_P <= 1):
            errors.append("INFERENCE_TOP_P must be between 0 and 1")
        if not (0 < cls.INFERENCE_TEMPERATURE <= 1):
            errors.append("INFERENCE_TEMPERATURE must be between 0 and 1")
        
        # Validate audio configuration
        if cls.AUDIO_INPUT_SAMPLE_RATE <= 0:
            errors.append("AUDIO_INPUT_SAMPLE_RATE must be greater than 0")
        if cls.AUDIO_OUTPUT_SAMPLE_RATE <= 0:
            errors.append("AUDIO_OUTPUT_SAMPLE_RATE must be greater than 0")
        
        return errors