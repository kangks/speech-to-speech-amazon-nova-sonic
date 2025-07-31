import os
import boto3
from datetime import datetime
from loguru import logger


class TranscriptHandler:
    def __init__(self, transport=None, username=None, session_id=None):
        self.messages = []
        # Store the transport if provided
        self.transport = transport
        
        # Store the username or use a default
        self.username = username or os.getenv("DEFAULT_USERNAME", "default_user")
        
        self.session_id = session_id or None

        # Initialize DynamoDB client if table name is provided
        self.dynamodb_client = None
        dynamodb_table_name = os.getenv("DYNAMODB_TABLE_NAME")
        if dynamodb_table_name:
            session = boto3.Session(profile_name=os.getenv("AWS_PROFILE", None))
            self.dynamodb_client = session.resource(
                "dynamodb",
                region_name=os.getenv("DYNAMODB_AWS_REGION", "us-east-1")
            ).Table(dynamodb_table_name)
            logger.info(f"DynamoDB integration enabled with table: {dynamodb_table_name}")
        
        # Schedule a test transcript message to be sent after initialization
        self.send_test_transcript = True

    async def on_transcript_update(self, processor, frame):
        self.messages.extend(frame.messages)
        
        # Log new messages with timestamps
        for msg in frame.messages:
            timestamp = f"[{msg.timestamp}] " if msg.timestamp else datetime.now().isoformat()
            message = f"{msg.role}: {msg.content}"
            print(f"{timestamp}{message}")
            
            # Store individual message in DynamoDB if configured
            await self.store_conversation(message)
                    
    # Function to store conversation in DynamoDB
    async def store_conversation(self, message, username=None):
        """Store conversation in DynamoDB."""
        if not self.dynamodb_client:
            logger.debug("DynamoDB integration not enabled, skipping storage")
            return

        try:
            # Use provided username or fall back to the instance username
            username = username or self.username
            timestamp = datetime.now().isoformat()
            conversation_id = f"{timestamp}"
            
            item = {
                "username": username,
                "session_id": self.session_id,
                "conversation_id": conversation_id,
                "timestamp": timestamp,
                "conversation": message
            }
            self.dynamodb_client.put_item(Item=item)
            logger.debug(f"Stored conversation in DynamoDB for user {username}: {conversation_id}")
        except Exception as e:
            logger.error(f"Error storing conversation in DynamoDB: {e}")
            
    def set_transport(self, transport):
        """Set the transport to use for sending messages to the frontend."""
        self.transport = transport
        logger.debug(f"[TRANSCRIPT DEBUG] Transport set: {transport.__class__.__name__}")
        
    def set_username(self, username):
        """Set the username for this transcript handler."""
        self.username = username
        logger.debug(f"[TRANSCRIPT DEBUG] Username set: {username}")
        
    
    async def on_participant_left(self, transport, participant, reason=None):
        """Handle participant left event by storing the full transcript in DynamoDB."""
        logger.info(f"Participant left: {participant}, reason: {reason}")
        
        # Store the full transcript in DynamoDB when a participant leaves
        if self.messages and self.dynamodb_client:
            try:
                username = self.username
                timestamp = datetime.now().isoformat()
                conversation_id = f"{username}_{timestamp.split('T')[0]}"
                
                # Create a formatted transcript with all messages
                full_transcript = []
                for msg in self.messages:
                    msg_timestamp = f"[{msg.timestamp}] " if msg.timestamp else ""
                    full_transcript.append({
                        "timestamp": msg_timestamp or datetime.now().isoformat(),
                        "role": msg.role,
                        "content": msg.content
                    })
                
                # Create the DynamoDB item - use same format as on_transcript_update for consistency
                item = {
                    "username": username,
                    "conversation_id": conversation_id,
                    "timestamp": timestamp,
                    "transcript_type": "final",  # Mark this as the final transcript
                    "full_transcript": full_transcript
                }
                
                self.dynamodb_client.put_item(Item=item)
                logger.info(f"Stored full transcript in DynamoDB on participant left for user {username}: {conversation_id}")
            except Exception as e:
                logger.error(f"Error storing full transcript in DynamoDB on participant left: {e}")