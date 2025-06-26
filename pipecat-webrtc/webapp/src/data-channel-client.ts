/**
 * WebRTC Data Channel Client for Nova Sonic
 * 
 * This module provides a client-side implementation for WebRTC data channel communication
 * with the Nova Sonic API server. It handles the WebRTC signaling, data channel setup,
 * and message handling for audio data transfer.
 */

export interface DataChannelClientConfig {
  apiEndpoint: string;
  iceServers: RTCIceServer[];
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: Error) => void;
  onMessage?: (message: any) => void;
  onAudioStart?: (metadata: any) => void;
  onAudioChunk?: (data: any) => void;
  onAudioEnd?: (data: any) => void;
}

export interface AudioMetadata {
  filename: string;
  fileSize: number;
  mimeType: string;
  totalChunks: number;
}

export class DataChannelClient {
  private config: DataChannelClientConfig;
  private peerConnection: RTCPeerConnection | null = null;
  private dataChannel: RTCDataChannel | null = null;
  private pcId: string | null = null;
  private connected: boolean = false;
  private connecting: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private baseReconnectDelay: number = 1000; // 1 second

  constructor(config: DataChannelClientConfig) {
    this.config = config;
  }

  /**
   * Connect to the WebRTC server
   */
  public async connect(): Promise<boolean> {
    if (this.connected || this.connecting) {
      return false;
    }

    this.connecting = true;
    console.log('Connecting to WebRTC server...');

    try {
      // Create peer connection with ICE servers
      this.peerConnection = new RTCPeerConnection({
        iceServers: this.config.iceServers,
        iceCandidatePoolSize: 10
      });

      // Set up ICE candidate handling
      this.peerConnection.onicecandidate = (event) => {
        if (event.candidate) {
          console.log(`Generated ICE candidate: ${event.candidate.candidate.substring(0, 50)}...`);
        } else {
          console.log('ICE candidate generation complete');
        }
      };

      // Set up connection state change handling
      this.peerConnection.oniceconnectionstatechange = () => {
        console.log(`ICE connection state changed: ${this.peerConnection?.iceConnectionState}`);
        
        if (this.peerConnection?.iceConnectionState === 'connected' ||
            this.peerConnection?.iceConnectionState === 'completed') {
          this.connected = true;
          this.connecting = false;
          this.reconnectAttempts = 0;
          this.config.onConnected?.();
        } else if (this.peerConnection?.iceConnectionState === 'failed' ||
                  this.peerConnection?.iceConnectionState === 'disconnected' ||
                  this.peerConnection?.iceConnectionState === 'closed') {
          this.connected = false;
          this.config.onDisconnected?.();
          console.error(`ICE connection failed: ${this.peerConnection.iceConnectionState}`);
          
          // Attempt reconnection
          if (!this.connecting) {
            this.handleReconnection();
          }
        }
      };

      // Create data channel
      this.dataChannel = this.peerConnection.createDataChannel('audio-channel', {
        ordered: true
      });

      // Set up data channel event handlers
      this.setupDataChannelHandlers();

      // Create offer
      const offer = await this.peerConnection.createOffer({
        offerToReceiveAudio: false,
        offerToReceiveVideo: false
      });

      // Set local description
      await this.peerConnection.setLocalDescription(offer);

      // Wait for ICE gathering to complete or timeout after 5 seconds
      await new Promise<void>((resolve) => {
        const checkState = () => {
          if (this.peerConnection?.iceGatheringState === 'complete') {
            console.log('ICE gathering complete');
            resolve();
          }
        };
        
        const gatheringTimeout = setTimeout(() => {
          console.warn('ICE gathering timed out, proceeding with available candidates');
          resolve();
        }, 5000);
        
        if (this.peerConnection) {
          this.peerConnection.onicegatheringstatechange = () => {
            console.log(`ICE gathering state changed: ${this.peerConnection?.iceGatheringState}`);
            checkState();
          };
        }
        
        checkState();
      });

      // Get the current offer with ICE candidates
      const currentOffer = this.peerConnection.localDescription;
      if (!currentOffer) {
        throw new Error('No local description available');
      }

      // Send offer to server
      console.log('Sending offer to server');
      const response = await fetch(this.config.apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          sdp: currentOffer.sdp,
          type: currentOffer.type,
          pc_id: this.pcId
        })
      });

      if (!response.ok) {
        throw new Error(`Server responded with status: ${response.status}`);
      }

      // Process answer
      const answer = await response.json();
      console.log(`Received answer from server: ${answer.type}`);

      // Store the pc_id if provided
      if (answer.pc_id) {
        this.pcId = answer.pc_id;
        console.log(`Received pc_id: ${this.pcId}`);
      }

      // Set remote description
      await this.peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
      console.log(`Remote description set: ${this.peerConnection.signalingState}`);

      return true;
    } catch (error) {
      this.connecting = false;
      const err = error as Error;
      this.config.onError?.(err);
      console.error('WebRTC connection error:', error);
      return false;
    }
  }

  /**
   * Disconnect from the WebRTC server
   */
  public async disconnect(): Promise<void> {
    try {
      if (this.dataChannel) {
        this.dataChannel.close();
        this.dataChannel = null;
      }

      if (this.peerConnection) {
        this.peerConnection.close();
        this.peerConnection = null;
      }

      this.connected = false;
      this.connecting = false;
      this.config.onDisconnected?.();
    } catch (error) {
      console.error('Error disconnecting:', error);
    }
  }

  /**
   * Send a message over the data channel
   */
  public sendMessage(message: any): boolean {
    if (this.dataChannel && this.dataChannel.readyState === 'open') {
      this.dataChannel.send(JSON.stringify(message));
      return true;
    } else {
      console.warn('Cannot send message: Data channel not open');
      return false;
    }
  }

  /**
   * Send audio data over the data channel
   */
  public async sendAudio(audioData: ArrayBuffer, filename: string, mimeType: string = 'audio/wav'): Promise<boolean> {
    if (!this.dataChannel || this.dataChannel.readyState !== 'open') {
      console.warn('Cannot send audio: Data channel not open');
      return false;
    }

    try {
      const chunkSize = 16 * 1024; // 16KB chunks
      const totalChunks = Math.ceil(audioData.byteLength / chunkSize);
      
      // Send start message with metadata
      this.sendMessage({
        type: 'audio-start',
        label: 'nova-sonic',
        data: {
          filename: filename,
          fileSize: audioData.byteLength,
          mimeType: mimeType,
          totalChunks
        }
      });
      
      // Send audio data in chunks
      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, audioData.byteLength);
        const chunk = audioData.slice(start, end);
        
        this.sendMessage({
          type: 'audio-chunk',
          label: 'nova-sonic',
          data: {
            chunkIndex: i,
            totalChunks,
            chunk: Array.from(new Uint8Array(chunk))
          }
        });
        
        // Small delay to prevent overwhelming the connection
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      
      // Send end message
      this.sendMessage({
        type: 'audio-end',
        label: 'nova-sonic',
        data: {
          filename: filename
        }
      });
      
      console.log('Audio file sent successfully');
      return true;
    } catch (error) {
      console.error('Error sending audio:', error);
      return false;
    }
  }

  /**
   * Handle reconnection with exponential backoff
   */
  private handleReconnection(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.connecting = true;
      
      // Calculate delay with exponential backoff
      const delay = this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts);
      this.reconnectAttempts++;
      
      console.log(`Connection lost. Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);
      
      // Attempt reconnection after delay
      setTimeout(async () => {
        // Clean up existing connection
        if (this.peerConnection) {
          this.peerConnection.close();
          this.peerConnection = null;
        }
        
        // Attempt to connect again
        this.connecting = false;
        await this.connect();
      }, delay);
    } else {
      console.log('Maximum reconnection attempts reached');
      this.connecting = false;
      this.config.onDisconnected?.();
    }
  }

  /**
   * Set up data channel event handlers
   */
  private setupDataChannelHandlers(): void {
    if (!this.dataChannel) return;

    this.dataChannel.onopen = () => {
      console.log('Data channel opened');
      this.connected = true;
      this.connecting = false;
      this.config.onConnected?.();
      
      // Send ready message
      this.sendMessage({
        type: 'client-ready',
        label: 'nova-sonic',
        data: {}
      });
    };

    this.dataChannel.onclose = () => {
      console.log('Data channel closed');
      this.connected = false;
      this.config.onDisconnected?.();
    };

    this.dataChannel.onerror = (error) => {
      console.error('Data channel error:', error);
      this.config.onError?.(new Error('Data channel error'));
    };

    this.dataChannel.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        // Handle different message types
        switch (message.type) {
          case 'audio-start':
            this.config.onAudioStart?.(message.data);
            break;
          case 'audio-chunk':
            this.config.onAudioChunk?.(message.data);
            break;
          case 'audio-end':
            this.config.onAudioEnd?.(message.data);
            break;
          default:
            // Forward to general message handler
            this.config.onMessage?.(message);
            break;
        }
      } catch (error) {
        console.error('Error processing message:', error);
      }
    };
  }

  /**
   * Check if the client is connected
   */
  public isConnected(): boolean {
    return this.connected;
  }

  /**
   * Check if the client is connecting
   */
  public isConnecting(): boolean {
    return this.connecting;
  }

  /**
   * Get the peer connection ID
   */
  public getPeerId(): string | null {
    return this.pcId;
  }
}