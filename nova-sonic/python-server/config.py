import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Centralized configuration management for the Nova Sonic Python server."""
    
    # Server configuration
    HOST = os.getenv("HOST", "0.0.0.0")  # Default to 0.0.0.0 for containerization
    WS_PORT = int(os.getenv("WS_PORT", "8081"))
    HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080")) if os.getenv("HEALTH_PORT") else None
    
    # Debug and logging
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LOGLEVEL = os.getenv("LOGLEVEL", "INFO").upper()
    LOG_FILE = os.getenv("LOG_FILE", None)
    
    # AWS configuration
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_PROFILE = os.getenv("AWS_PROFILE")
    
    # Nova Sonic configuration
    NOVA_SONIC_MODEL_ID = os.getenv("NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0")
    
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
        
        return errors