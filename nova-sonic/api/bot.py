import argparse
import asyncio
import os
import uuid
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.aws_nova_sonic import AWSNovaSonicLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.network.small_webrtc import SmallWebRTCTransport
from pipecat.transports.network.webrtc_connection import SmallWebRTCConnection

from transcript_handler import TranscriptHandler
from function_schema import tools, register_functions


async def run_bot(webrtc_connection: SmallWebRTCConnection, args: argparse.Namespace):
    """Run the Nova Sonic bot with the given WebRTC connection."""
    logger.info("Starting Nova Sonic bot")
    
    # Generate a unique conversation ID
    conversation_id = str(uuid.uuid4())
    logger.info(f"New conversation started: {conversation_id}")
    
    # Initialize the SmallWebRTCTransport with the connection
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_enabled=True,
            camera_in_enabled=False,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.8)),
        ),
    )

    # Specify initial system instruction
    system_instruction = (
        """You are a professional AI Interviewer specializing in technical job interviews. Your role is to assess candidate qualifications through thoughtful, relevant questions.
            You are capable of understanding and responding to candidates in a natural and engaging manner while maintaining a professional tone.
            You and the candidate will engage in a spoken dialog exchanging the transcripts of a natural real-time conversation.
            
            Your primary responsibilities:
            1. Ask the candidate which position they are applying for
            2. Use the get_job_questions function with the position parameter to retrieve relevant interview questions
            3. Ask the questions provided by the function to assess the candidate's qualifications
            4. Maintain a professional interviewing tone throughout the conversation
            5. Adapt to the specific technical domain of the position the candidate is applying for
            
            Start the conversation by introducing yourself as an AI Interviewer, then ask for the candidate's name.
            After greeting them by name, ask which position they are applying for today.
            
            Once you know the position, use the get_job_questions function with the position parameter to get relevant questions.
            If the position doesn't match any in our database, use your judgment to ask appropriate technical questions for similar roles.
            
            IMPORTANT: Each question includes an "expectation" field that describes what a good answer should include.
            Use these expectations to evaluate the candidate's responses and guide your follow-up questions.
            For example, if a question about microservices has an expectation that mentions "service communication approaches",
            and the candidate doesn't address this in their answer, you can ask a follow-up specifically about that topic.
            DO NOT disclose the expectations to the candidate; they are for your internal use only.
            
            The interview concludes when you've asked all the questions from get_job_questions and received responses, or when the candidate explicitly states they want to end the conversation.
            If the candidate answers irrelevant questions or provides answers that are not related to the position, gently redirect them back to the topic. End the interview if the candidate consistently does so after 5 attempts.
            At the end, thank the candidate for their time and provide a brief summary of their strengths based on their responses.
        """
        f"{AWSNovaSonicLLMService.AWAIT_TRIGGER_ASSISTANT_RESPONSE_INSTRUCTION}"
    )

    region = os.getenv("AWS_REGION", "us-east-1")
    voice_id = os.getenv("NOVA_SONIC_VOICE_ID", "tiffany")

    # Create the AWS Nova Sonic LLM service
    llm = AWSNovaSonicLLMService(
        secret_access_key=os.getenv("NOVA_AWS_SECRET_ACCESS_KEY"),
        access_key_id=os.getenv("NOVA_AWS_ACCESS_KEY_ID"),
        region=os.getenv("NOVA_AWS_REGION"),
        voice_id=voice_id,  # matthew, tiffany, amy
        send_transcription_frames=True
    )
    
    # Register functions for function calls
    register_functions(llm)

    # Set up context and context management
    context = OpenAILLMContext(
        messages=[
            {"role": "system", "content": f"{system_instruction}"},
            {
                "role": "user",
                "content": "Hello, I'm here for my interview.",
            },
        ],
        tools=tools,
    )
    context_aggregator = llm.create_context_aggregator(context)

    # Initialize AWS Transcribe STT service
    # This is causing error now:
    # 2025-05-17 21:44:15.950 | DEBUG    | pipecat.services.aws.stt:_connect:212 - AWSTranscribeSTTService#1 Connecting to WebSocket with URL: wss://transcribestreaming.us-east-1.amazonaws.com:8443/stream-transcription-websocket?X-Amz-Algorith...
    # 2025-05-17 21:44:15.951 | ERROR    | pipecat.services.aws.stt:_connect:232 - AWSTranscribeSTTService#1 Failed to connect to AWS Transcribe: create_connection() got an unexpected keyword argument 'extra_headers'
    # stt_service = AWSTranscribeSTTService(
    #     secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    #     access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    #     region=region,
    #     sample_rate=16000,
    #     language=Language.EN
    # )
    
    # Create a callback handler for transcription events
    transcript = TranscriptProcessor()
    transcript_handler = TranscriptHandler(transport)

    # Build the pipeline
    pipeline = Pipeline(
        [
            transport.input(),
            context_aggregator.user(),
            llm,
            ParallelPipeline(
            [
                transcript.user(),              # Captures user transcripts
                transcript.assistant(),         # Captures assistant transcripts
                transport.output(),
            ]),
            context_aggregator.assistant(),
        ]
    )
    
    # Note: We can't use event handlers for transcriptions because the services don't support them
    # Instead, we'll rely on the DynamoDB integration for storing conversations if needed

    # Configure the pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transcript.event_handler("on_transcript_update")
    async def handle_transcript_update(processor, frame):
        await transcript_handler.on_transcript_update(processor, frame)
            
    # Handle client connection event
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        # Ensure the transcript handler has the latest transport
        transcript_handler.set_transport(transport)
        logger.info("Updated transport in transcript handler")
        
        # Kick off the conversation
        await task.queue_frames([context_aggregator.user().get_context_frame()])
        # Trigger the first assistant response
        await llm.trigger_assistant_response()
        
        # Send test transcript messages to verify transcript functionality
        logger.info("Sending test transcript messages")
        await transcript_handler.send_test_transcript_message(transcript)

    # Handle client disconnection events
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")

    @transport.event_handler("on_client_closed")
    async def on_client_closed(transport, client):
        logger.info("Client closed connection")
        await task.cancel()

    # Run the pipeline
    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    except Exception as e:
        logger.error(f"Error running pipeline: {e}")
        raise