# Amazon Nova Sonic Speech-to-Speech Implementation

This directory contains a complete implementation of a speech-to-speech conversational AI system using Amazon Nova Sonic. The system enables real-time voice conversations between users and an AI assistant through a web browser interface.

## Table of Contents

- [Amazon Nova Sonic Speech-to-Speech Implementation](#amazon-nova-sonic-speech-to-speech-implementation)
  - [Table of Contents](#table-of-contents)
  - [Architecture Overview](#architecture-overview)
  - [Server-Side Implementation](#server-side-implementation)
    - [FastAPI Server](#fastapi-server)
    - [Bot Implementation](#bot-implementation)
    - [Pipeline Architecture](#pipeline-architecture)
  - [Client-Side Implementation](#client-side-implementation)
    - [WebRTC Communication](#webrtc-communication)
    - [Media Handling](#media-handling)
    - [User Interface](#user-interface)
  - [AWS Deployment Architecture](#aws-deployment-architecture)
    - [Infrastructure as Code](#infrastructure-as-code)
    - [Containerization](#containerization)
    - [Networking](#networking)
    - [Security](#security)
  - [AWS Architecture Diagram](#aws-architecture-diagram)
  - [Getting Started](#getting-started)
  - [Environment Variables](#environment-variables)
    - [Server Environment Variables](#server-environment-variables)
    - [Client Environment Variables](#client-environment-variables)

## Architecture Overview

The Amazon Nova Sonic Speech-to-Speech implementation is built on a modern, distributed architecture that enables real-time bidirectional voice communication between users and an AI assistant. The system consists of three main components:

1. **Server**: A FastAPI-based backend that manages connections, creates communication rooms, and spawns AI bot instances
2. **Bot**: A sophisticated pipeline that processes audio streams, transcribes speech, generates responses using Amazon Nova Sonic, and synthesizes speech
3. **Client**: A browser-based frontend that handles WebRTC connections, audio/video streaming, and user interactions

The system uses WebRTC (via Daily's transport layer) for real-time communication, enabling low-latency, high-quality audio streaming in both directions. The entire infrastructure is deployed on AWS using containerized services for scalability and reliability.

## Server-Side Implementation

### FastAPI Server

The server implementation (`server.py`) provides the foundation for the speech-to-speech system:

- Built with FastAPI for high-performance API endpoints
- Manages client connections and authentication
- Creates Daily rooms for WebRTC communication
- Spawns and monitors Amazon Nova Sonic bot instances
- Provides health check and status endpoints

Key server endpoints:

- `/connect`: Creates a Daily room and returns connection credentials
- `/health`: Health check endpoint for monitoring
- `/status/{pid}`: Gets the status of a specific bot process

### Bot Implementation

The bot implementation (`bot_bedrock_nova.py`) handles the core AI functionality:

- Establishes bidirectional WebRTC connections using DailyTransport
- Processes audio streams using voice activity detection
- Transcribes user speech to text
- Generates contextual responses using Amazon Nova Sonic LLM
- Synthesizes speech from text responses
- Manages visual animations for the bot interface

### Pipeline Architecture

The bot uses a sophisticated pipeline architecture for processing:

1. **Input Stage**: Captures audio from WebRTC and processes it through voice activity detection
2. **Transcription**: Converts speech to text
3. **Context Management**: Maintains conversation context using OpenAILLMContext
4. **Language Processing**: Generates responses using AWSNovaSonicLLMService
5. **Speech Synthesis**: Converts text responses to speech
6. **Output Stage**: Streams synthesized speech and visual animations back to the client

The pipeline is designed for real-time processing with minimal latency, enabling natural conversational flow.

## Client-Side Implementation

### WebRTC Communication

The client implementation (`app.js`) establishes and manages the WebRTC connection:

- Uses the RTVI client library for standardized communication
- Connects to the server's `/connect` endpoint to obtain room credentials
- Establishes a WebRTC connection via DailyTransport
- Handles connection state changes and reconnection logic

### Media Handling

The client manages audio and video streams:

- Captures user microphone input
- Processes incoming bot audio for playback
- Displays bot video/animations
- Handles media track events (start/stop)
- Manages media resources cleanup on disconnection

### User Interface

The client provides a simple but effective user interface:

- Connect/disconnect controls
- Connection status display
- Transcript display for both user and bot speech
- Visual feedback through bot animations
- Debug logging for troubleshooting

## AWS Deployment Architecture

### Infrastructure as Code

The entire infrastructure is defined using AWS CDK with TypeScript:

- Enables reproducible deployments
- Manages all AWS resources as code
- Simplifies updates and modifications
- Provides consistent environments

### Containerization

Both server and client components are containerized:

- **Server Container**:
  - Python FastAPI application
  - Deployed on AWS Fargate
  - Configured with appropriate memory and CPU resources
  - Environment variables and secrets managed securely

- **Client Container**:
  - Vite-based web application
  - Nginx for static file serving
  - Deployed on AWS Fargate
  - Configured for optimal performance

### Networking

The architecture includes comprehensive networking:

- Custom VPC with public and private subnets
- Application Load Balancers for both server and client
- HTTPS with SSL/TLS certificates
- Custom domain names via Route 53
- Health checks and monitoring

### Security

Security is implemented at multiple levels:

- HTTPS for all communications
- Secrets stored in AWS Parameter Store
- Environment-specific configuration
- Proper IAM roles and permissions
- Network security groups

## AWS Architecture Diagram

![Amazon Nova Sonic Speech-to-Speech Architecture](generated-diagrams/nova-sonic-architecture.png)

The diagram above illustrates the AWS architecture of the speech-to-speech implementation:

1. Users connect to the client application through a load balancer
2. The client application runs in a Fargate container in a private subnet
3. The client communicates with the server through WebRTC/HTTPS
4. The server runs in a separate Fargate container in a private subnet
5. The server communicates with Amazon Nova Sonic for language processing
6. Supporting services include Route 53 for DNS, ACM for certificates, S3 for storage, and CloudWatch for logging

## Getting Started

To run the application locally:

1. Clone the repository
2. Set up environment variables (see below)
3. Start the server:
   ```
   cd daily/server
   pip install -r requirements.txt
   python server.py
   ```
4. Start the client:
   ```
   cd daily/vite-client
   npm install
   npm run dev
   ```

## Environment Variables

### Server Environment Variables

- `DAILY_API_KEY`: API key for Daily.co
- `DAILY_API_URL`: URL for Daily API (default: https://api.daily.co/v1)
- `NOVA_AWS_ACCESS_KEY_ID`: AWS access key for Nova Sonic
- `NOVA_AWS_SECRET_ACCESS_KEY`: AWS secret key for Nova Sonic
- `NOVA_AWS_REGION`: AWS region for Nova Sonic (default: us-east-1)
- `NOVA_VOICE_ID`: Voice ID for Nova Sonic (default: tiffany)

### Client Environment Variables

- `VITE_BASE_URL`: Base URL for the server API (default: http://localhost:8000)