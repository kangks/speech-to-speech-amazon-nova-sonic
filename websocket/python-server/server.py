import asyncio
import websockets
import json
import logging
import http.server
import threading
import os
import time
from http import HTTPStatus
from s2s_session_manager import S2sSessionManager
from s2s_events import S2sEvent
from integration.strands_agent import StrandsAgent
from config import Config

# Configure logging
Config.configure_logging()
logger = logging.getLogger(__name__)

MCP_CLIENT = None
STRANDS_AGENT = None

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        client_ip = self.client_address[0]
        logger.info(
            f"Health check request received from {client_ip} for path: {self.path}"
        )

        if self.path == "/health" or self.path == "/":
            logger.info(f"Responding with 200 OK to health check from {client_ip}")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = json.dumps({"status": "healthy"})
            self.wfile.write(response.encode("utf-8"))
            logger.info(f"Health check response sent: {response}")
        else:
            logger.info(
                f"Responding with 404 Not Found to request for {self.path} from {client_ip}"
            )
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def log_message(self, format, *args):
        # Override to use our logger instead
        pass

def start_health_check_server(health_host, health_port):
    """Start the HTTP health check server on port 80."""
    try:
        # Create the server with a socket timeout to prevent hanging
        httpd = http.server.HTTPServer((health_host, health_port), HealthCheckHandler)
        httpd.timeout = 5  # 5 second timeout

        logger.info(f"Starting health check server on {health_host}:{health_port}")

        # Run the server in a separate thread
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = (
            True  # This ensures the thread will exit when the main program exits
        )
        thread.start()

        # Verify the server is running
        logger.info(
            f"Health check server started at http://{health_host}:{health_port}/health"
        )
        logger.info(f"Health check thread is alive: {thread.is_alive()}")

        # Try to make a local request to verify the server is responding
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"http://localhost:{health_port}/health", timeout=2
            ) as response:
                logger.info(
                    f"Local health check test: {response.status} - {response.read().decode('utf-8')}"
                )
        except Exception as e:
            logger.warning(f"Local health check test failed: {e}")

    except Exception as e:
        logger.error(f"Failed to start health check server: {e}", exc_info=True)


async def websocket_handler(websocket):
    stream_manager = None
    keepalive_task = None
    logger.debug("WebSocket connection established")
    try:
        # Start the keepalive task immediately to prevent ALB from closing the connection
        keepalive_task = asyncio.create_task(websocket_keepalive(websocket))
        
        async for message in websocket:
            try:
                data = json.loads(message)
                if 'body' in data:
                    data = json.loads(data["body"])
                if 'event' in data:
                    if stream_manager == None:

                        # Initialize the stream manager with the model ID and reg
                        prompt_name=data['event'].get('init', {}).get('promptName', '')
                        text_content_name=data['event'].get('init', {}).get('textContentName', '')
                        audio_content_name=data['event'].get('init', {}).get('audioContentName', '')

                        logger.info(f"Initializing stream manager with prompt: {prompt_name}, text content: {text_content_name}, audio content: {audio_content_name}")

                        """Handle WebSocket connections from the frontend."""
                        # Create a new stream manager for this connection
                        stream_manager = S2sSessionManager(
                            model_id=Config.NOVA_SONIC_MODEL_ID,
                            region=Config.AWS_DEFAULT_REGION,
                            mcp_client=MCP_CLIENT,
                            strands_agent=STRANDS_AGENT,
                            prompt_name=prompt_name,
                            text_content_name=text_content_name,
                            audio_content_name=audio_content_name

                        )

                        # Initialize the Bedrock stream
                        await stream_manager.initialize_stream()
                        
                        # Start a task to forward responses from Bedrock to the WebSocket
                        forward_task = asyncio.create_task(forward_responses(websocket, stream_manager))

                    event_type = list(data['event'].keys())[0]
                    if event_type == "audioInput":
                        logger.debug(message[0:180])
                    else:
                        logger.debug(message)
                            
                    if event_type:
                        if event_type == 'init':
                            logger.info(f"Received event: {event_type}")
                        # Handle audio input separately
                        elif event_type == 'audioInput':
                            # Extract audio data
                            prompt_name = data['event']['audioInput']['promptName']
                            content_name = data['event']['audioInput']['contentName']
                            audio_base64 = data['event']['audioInput']['content']
                            # logger.info(f"Received audio input for prompt: {prompt_name}, content: {content_name}") 
                            # Add to the audio queue
                            stream_manager.add_audio_chunk(prompt_name, content_name, audio_base64)
                        elif event_type == 'sessionEnd':
                            logger.info(f"Received event: {event_type}")
                            try:
                                # Handle session end event
                                await stream_manager.send_raw_event(data)
                                logger.info("Session end event received, closing connection")
                                
                                # Gracefully close the stream manager before closing the WebSocket
                                await stream_manager.close()
                                
                                # Set stream_manager to None to prevent double cleanup in finally block
                                stream_manager = None
                                
                                # Break out of the message loop to close the WebSocket connection
                                break
                            except Exception as e:
                                logger.warning(f"Error during session end handling: {str(e)}")
                                # Continue to finally block for cleanup
                                break
                        elif event_type == 'contentEnd':
                            logger.info(f"Received event: {event_type}")
                            # Handle session end event
                            await stream_manager.send_raw_event(data)
                            logger.info("Content end event received, closing connection")
                        elif event_type == 'promptEnd':
                            logger.info(f"Received event: {event_type}")
                            # Handle session end event
                            await stream_manager.send_raw_event(data)
                            logger.info("Prompt end event received, closing connection")
                        elif event_type == 'ping':
                            # Handle ping event - just log it, no need to forward to Bedrock
                            logger.debug("Received ping response from client")
                            # Optionally send a pong response if needed
                            # await websocket.send(json.dumps(S2sEvent.ping()))
                        else:
                            logger.info(f"Received event in else: {event_type}")
                            # For backward compatibility, send other events directly to Bedrock
                            await stream_manager.send_raw_event(data)
            except json.JSONDecodeError:
                logger.exception("Invalid JSON received from WebSocket")
            except Exception as e:
                logger.exception(f"Error processing WebSocket message: {e}")
    except websockets.exceptions.ConnectionClosed:
        logger.exception("WebSocket connection closed")
    except Exception as e:
        logger.exception(f"Error in websocket handler: {e}")
    finally:
        # Clean up
        if stream_manager:
            await stream_manager.close()
        if 'forward_task' in locals() and forward_task:
            forward_task.cancel()
        if 'keepalive_task' in locals() and keepalive_task:
            keepalive_task.cancel()
        if websocket:
            websocket.close()
        if MCP_CLIENT:
            MCP_CLIENT.cleanup()


async def websocket_keepalive(websocket):
    """Send periodic ping frames to keep the WebSocket connection alive."""
    try:
        while True:
            try:
                # Send a ping frame every 30 seconds
                # This will help prevent the ALB from closing the connection due to inactivity
                await asyncio.sleep(30)
                
                # Create a ping event using the S2sEvent class
                ping_event = S2sEvent.ping()
                
                # Send the ping event
                await websocket.send(json.dumps(ping_event))
                logger.debug("Sent WebSocket keepalive ping")
                
            except websockets.exceptions.ConnectionClosed:
                logger.debug("WebSocket closed, stopping keepalive")
                break
            except Exception as e:
                logger.warning(f"Error in WebSocket keepalive: {str(e)}")
                # Continue the loop to try again
    except asyncio.CancelledError:
        # Task was cancelled
        pass
    except Exception as e:
        logger.exception(f"Unhandled error in keepalive task: {e}")


async def forward_responses(websocket, stream_manager):
    """Forward responses from Bedrock to the WebSocket."""
    try:
        while True:
            # Get next response from the output queue
            response = await stream_manager.output_queue.get()
            
            # Send to WebSocket
            try:
                event = json.dumps(response)
                await websocket.send(event)
            except websockets.exceptions.ConnectionClosed:
                break
    except asyncio.CancelledError:
        # Task was cancelled
        pass
    except Exception as e:
        logger.exception(f"Error forwarding responses: {e}")
        # Close connection
        websocket.close()
        stream_manager.close()


async def main():
    errors = Config.validate()
    if errors:
        for error in errors:
            logger.error(error)
        exit(1)

    """Main function to run the WebSocket server."""
    host = Config.HOST
    port = Config.WS_PORT
    health_port = Config.HEALTH_PORT
    
    if health_port:
        try:
            start_health_check_server(host, health_port)
        except Exception as ex:
            logger.error(f"Failed to start health check endpoint: {ex}")
    
    # Init Strands Agent
    if Config.ENABLE_STRANDS_AGENT:
        logger.info("Strands agent enabled")
        try:
            global STRANDS_AGENT
            STRANDS_AGENT = StrandsAgent()
        except Exception as ex:
            logger.exception(f"Failed to start Strands agent: {ex}")

    try:
        # Start WebSocket server
        async with websockets.serve(websocket_handler, host, port):
            logger.info(f"WebSocket server started at host:{host}, port:{port}")
            
            # Keep the server running forever
            await asyncio.Future()
    except Exception as ex:
        logger.error(f"Failed to start websocket service: {ex}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.exception(f"Server error: {e}")
    finally:
        if MCP_CLIENT:
            MCP_CLIENT.cleanup()