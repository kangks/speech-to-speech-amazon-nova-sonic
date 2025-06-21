class VADProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.volumeSum = 0;
    this.sampleCount = 0;
    this.silenceThreshold = 0.015;
    this.volumeHistory = new Array(10).fill(0);
    this.historyIndex = 0;
    this.vadActive = false;
    this.consecutiveVoiceFrames = 0;
    this.consecutiveSilenceFrames = 0;
    this.voiceDetectionThreshold = 3; // Number of frames to consider as voice
    this.silenceDetectionThreshold = 5; // Number of frames to consider as silence
  }
  
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    
    const samples = input[0];
    let sum = 0;
    
    // Calculate RMS volume
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    
    const rms = Math.sqrt(sum / samples.length);
    
    // Update volume history
    this.volumeHistory[this.historyIndex] = rms;
    this.historyIndex = (this.historyIndex + 1) % this.volumeHistory.length;
    
    // Calculate average volume
    const avgVolume = this.volumeHistory.reduce((a, b) => a + b, 0) / this.volumeHistory.length;
    
    // Determine if voice is active
    const isSpeaking = avgVolume > this.silenceThreshold;
    
    // Use hysteresis to prevent rapid switching
    if (isSpeaking) {
      this.consecutiveVoiceFrames++;
      this.consecutiveSilenceFrames = 0;
      
      if (this.consecutiveVoiceFrames >= this.voiceDetectionThreshold && !this.vadActive) {
        this.vadActive = true;
        this.port.postMessage({ vadActive: true, volume: avgVolume });
      }
    } else {
      this.consecutiveSilenceFrames++;
      this.consecutiveVoiceFrames = 0;
      
      if (this.consecutiveSilenceFrames >= this.silenceDetectionThreshold && this.vadActive) {
        this.vadActive = false;
        this.port.postMessage({ vadActive: false, volume: avgVolume });
      }
    }
    
    // Send volume updates periodically (every 10 frames)
    if ((this.sampleCount % 10) === 0) {
      this.port.postMessage({ vadActive: this.vadActive, volume: avgVolume });
    }
    
    this.sampleCount++;
    
    return true;
  }
}

registerProcessor('vad-processor', VADProcessor);