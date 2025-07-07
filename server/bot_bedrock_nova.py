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
from pipecat.services.aws_nova_sonic import AWSNovaSonicLLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport

from bot_tools import function_tools_schema, register_functions

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

        # try:
        #     mcp = await get_mcp_client()
        # except Exception as e:
        #     logger.error(f"error setting up mcp")
        #     logger.exception("error trace:")

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
        # Create the AWS Nova Sonic LLM service
        llm = AWSNovaSonicLLMService(
            secret_access_key=NOVA_AWS_SECRET_ACCESS_KEY,
            access_key_id=NOVA_AWS_ACCESS_KEY_ID,
            region=os.getenv("NOVA_AWS_REGION", "us-east-1"),
            voice_id=os.getenv("NOVA_VOICE_ID", "tiffany"),  # matthew, tiffany, amy
            send_transcription_frames=True
        )        

        register_functions(llm)

        # mcp_tool = await mcp.register_tools(llm)
        # print(dir(mcp_tool))
        # print(mcp_tool.standard_tools)
        # tools_mcp_schema = function_tools
        # tools_mcp_schema = ToolsSchema(toolsSchema.standard_tools + mcp_tool.standard_tools)

        system_instruction = (
            """<role>Professional AI Technical Interviewer</role>

        <context>
        You are conducting a live technical job interview via spoken conversation. The candidate can hear and speak with you in real-time.
        </context>

        <goals>
        - Assess candidate qualifications for their specific technical role
        - Maintain professional, engaging conversation
        - Use provided tools to retrieve and evaluate against job-specific questions
        </goals>

        <interview_process>
        1. INTRODUCTION: Introduce yourself as an AI Interviewer and read out all avaialble positions by calling the list jobs function
        2. POSITION IDENTIFICATION: Ask which position they're applying for
        3. QUESTION RETRIEVAL: Use InterviewGuestionsFunction(position) to retrieve relevant questions
        4. ASSESSMENT: Ask questions and evaluate responses against expectations
        5. CONCLUSION: Summarize candidate strengths and thank them
        </interview_process>

        <evaluation_guidelines>
        - Compare responses against question "expectation" fields
        - Identify missing key concepts from expectations
        - Ask targeted follow-up questions for missing concepts
        - Track response quality: (Strong/Moderate/Needs Improvement)
        - NEVER reveal expectations to candidates
        </evaluation_guidelines>

        <conversation_management>
        - Keep responses concise (2-3 sentences per turn)
        - Allow candidate to finish speaking before responding
        - If candidate goes off-topic, redirect after maximum 5 attempts
        - Signal interview progression ("Let's move to the next question about...")
        - Adapt technical depth based on candidate's demonstrated expertise
        </conversation_management>

        <response_templates>
        Introduction: "Hello, I'm your AI Technical Interviewer. May I have your name please?"
        Positions Available: "Here are the available positions: [list of positions]. Which position are you applying for today?"
        Question Format: "Let's discuss [topic]. [Clear, concise question]"
        Follow-up: "You mentioned [point], could you elaborate specifically on [missing expectation]?"
        Redirection: "I appreciate your thoughts, but let's focus on [relevant topic] for this position."
        Conclusion: "Thank you for your time today. Based on our conversation, your strengths include [specific strengths]."
        </response_templates>"""
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
            tools=function_tools_schema,
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
