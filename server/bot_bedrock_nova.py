import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from PIL import Image
from runner import configure

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    OutputImageRawFrame,
    SpriteFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.aws_nova_sonic import AWSNovaSonicLLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from bot_tools import toolsSchema, register_functions
from integration.average_salary_mcp_client import get_mcp_client

load_dotenv(override=True)
# logger.remove(0)
logger.add(sys.stdout, level="DEBUG")
logger.add("bot_bedrock_nova.err", level="ERROR")
logger.add("bot_bedrock_nova.log", level="DEBUG")

sprites = []
script_dir = os.path.dirname(__file__)

# Load sequential animation frames
for i in range(1, 26):
    # Build the full path to the image file
    full_path = os.path.join(script_dir, f"assets/robot0{i}.png")
    # Get the filename without the extension to use as the dictionary key
    # Open the image and convert it to bytes
    with Image.open(full_path) as img:
        sprites.append(OutputImageRawFrame(image=img.tobytes(), size=img.size, format=img.format))

# Create a smooth animation by adding reversed frames
flipped = sprites[::-1]
sprites.extend(flipped)

# Define static and animated states
quiet_frame = sprites[0]  # Static frame for when bot is listening
talking_frame = SpriteFrame(images=sprites)  # Animation sequence for when bot is talking


class TalkingAnimation(FrameProcessor):
    """Manages the bot's visual animation states.

    Switches between static (listening) and animated (talking) states based on
    the bot's current speaking status.
    """

    def __init__(self):
        super().__init__()
        self._is_talking = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and update animation state.

        Args:
            frame: The incoming frame to process
            direction: The direction of frame flow in the pipeline
        """
        await super().process_frame(frame, direction)

        # Switch to talking animation when bot starts speaking
        if isinstance(frame, BotStartedSpeakingFrame):
            if not self._is_talking:
                await self.push_frame(talking_frame)
                self._is_talking = True
        # Return to static frame when bot stops speaking
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self.push_frame(quiet_frame)
            self._is_talking = False

        await self.push_frame(frame, direction)


async def bot_main():
    """Main bot execution function.

    Sets up and runs the bot pipeline including:
    - Daily video transport
    - Speech-to-text and text-to-speech services
    - Language model integration
    - Animation processing
    - RTVI event handling
    """
    # Import here to avoid circular dependency
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        try:
            mcp = await get_mcp_client()
        except Exception as e:
            logger.error(f"error setting up mcp")
            logger.exception("error trace:")

        # Set up Daily transport with video/audio parameters
        transport = DailyTransport(
            room_url,
            token,
            "Chatbot",
            DailyParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                video_in_enabled=True,
                video_out_enabled=True,
                video_out_width=1024,
                video_out_height=576,
                vad_analyzer=SileroVADAnalyzer(),
                transcription_enabled=True,
            ),
        )

        NOVA_AWS_SECRET_ACCESS_KEY=os.getenv("NOVA_AWS_SECRET_ACCESS_KEY")
        NOVA_AWS_ACCESS_KEY_ID=os.getenv("NOVA_AWS_ACCESS_KEY_ID")
        logger.info(f"NOVA_AWS_ACCESS_KEY_ID: {NOVA_AWS_ACCESS_KEY_ID}")
        logger.info(f"NOVA_AWS_SECRET_ACCESS_KEY: {NOVA_AWS_SECRET_ACCESS_KEY}")

        # Initialize LLM service
        # llm = AWSNovaSonicLLMService(api_key=os.getenv("OPENAI_API_KEY"))
        # Create the AWS Nova Sonic LLM service
        llm = AWSNovaSonicLLMService(
            secret_access_key=NOVA_AWS_SECRET_ACCESS_KEY,
            access_key_id=NOVA_AWS_ACCESS_KEY_ID,
            region=os.getenv("NOVA_AWS_REGION", "us-east-1"),
            voice_id=os.getenv("NOVA_VOICE_ID", "tiffany"),  # matthew, tiffany, amy
            send_transcription_frames=True
        )        

        register_functions(llm)
        mcp_tool = await mcp.register_tools(llm)
        # print(dir(mcp_tool))
        # print(mcp_tool.standard_tools)
        tools_mcp_schema = ToolsSchema(toolsSchema.standard_tools + mcp_tool.standard_tools)

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

        # Set up context and context management
        context = OpenAILLMContext(
            messages=[
                {"role": "system", "content": f"{system_instruction}"},
                {
                    "role": "user",
                    "content": "Hello, I'm here for my interview.",
                },
            ],
            tools=tools_mcp_schema,
        )
        context_aggregator = llm.create_context_aggregator(context)

        ta = TalkingAnimation()

        #
        # RTVI events for Pipecat client UI
        #
        rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

        pipeline = Pipeline(
            [
                transport.input(),
                rtvi,
                context_aggregator.user(),
                llm,
                ta,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        # start_recording_status =await transport.start_recording()
        # # start_recording_status = await daily_helpers["rest"].start_recording(room_url, token)
        # print(f"Start recording status: {start_recording_status}")

        # await transport.start_recording()

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
            observers=[RTVIObserver(rtvi)],
        )
        await task.queue_frame(quiet_frame)

        @rtvi.event_handler("on_client_ready")
        async def on_client_ready(rtvi):
            await rtvi.set_bot_ready()
            # Kick off the conversation
            await task.queue_frames([context_aggregator.user().get_context_frame()])

        # Handle client connection event
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected")
            logger.info("Updated transport in transcript handler")
            
            # Kick off the conversation
            await task.queue_frames([context_aggregator.user().get_context_frame()])
            # Trigger the first assistant response
            await llm.trigger_assistant_response()
            
            # Send test transcript messages to verify transcript functionality
            logger.info("Sending test transcript messages")

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            print(f"Participant joined: {participant}")
            await transport.start_recording()
            await transport.capture_participant_transcription(participant["id"])

        @transport.event_handler("on_recording_started")
        async def on_recording_started(any1, any2):
            print(f"any1: {any1}")
            print(f"any2: {any2}")

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            print(f"Participant left: {participant}")
            # First, gracefully stop the LLM service
            try:
                # Add a method to the LLM service to close streams properly
                # await llm.close_streams()
                await transport.stop_recording()
            except Exception as e:
                logger.error(f"Error closing LLM streams: {e}")

            await task.cancel()

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(bot_main())
