/**
 * S2sEvent class for handling WebSocket events
 * Provides methods for creating event objects for the WebSocket protocol
 */
class S2sEvent {
    // Default inference configuration
    static DEFAULT_INFER_CONFIG = {
        maxTokens: 1024,
        topP: 0.95,
        temperature: 0.7
    };
  
    // Default system prompt
    static DEFAULT_SYSTEM_PROMPT = "You are a friend. The user and you will engage in a spoken dialog exchanging the transcripts of a natural real-time conversation. Keep your responses short, generally two or three sentences for chatty scenarios.";
  
    // Default audio input configuration
    static DEFAULT_AUDIO_INPUT_CONFIG = {
        mediaType: "audio/lpcm",
        sampleRateHertz: 16000,
        sampleSizeBits: 16,
        channelCount: 1,
        audioType: "SPEECH",
        encoding: "base64"
    };
  
    // Default audio output configuration
    static DEFAULT_AUDIO_OUTPUT_CONFIG = {
        mediaType: "audio/lpcm",
        sampleRateHertz: 24000,
        sampleSizeBits: 16,
        channelCount: 1,
        voiceId: "matthew",
        encoding: "base64",
        audioType: "SPEECH"
    };
  
    // Default tool configuration
    static DEFAULT_TOOL_CONFIG = {
        tools: [
            {
                toolSpec: {
                    name: "getDateTool",
                    description: "get information about the date and time",
                    inputSchema: {
                        json: JSON.stringify({
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                }
            }
        ]
    };

    // Default chat history
    static DEFAULT_CHAT_HISTORY = [
        {
            "content": "hi there",
            "role": "USER"
        },
        {
            "content": "Hello! How can I help you today?",
            "role": "ASSISTANT"
        }
    ];
  
    /**
     * Create a sessionStart event
     * @param {Object} inferenceConfig - Inference configuration
     * @returns {Object} - sessionStart event
     */
    static sessionStart(inferenceConfig = S2sEvent.DEFAULT_INFER_CONFIG) {
        return { event: { sessionStart: { inferenceConfiguration: inferenceConfig } } };
    }
  
    /**
     * Create a promptStart event
     * @param {string} promptName - Prompt name
     * @param {Object} audioOutputConfig - Audio output configuration
     * @param {Object} toolConfig - Tool configuration
     * @returns {Object} - promptStart event
     */
    static promptStart(promptName, audioOutputConfig = S2sEvent.DEFAULT_AUDIO_OUTPUT_CONFIG, toolConfig = S2sEvent.DEFAULT_TOOL_CONFIG) {
        return {
            "event": {
                "promptStart": {
                    "promptName": promptName,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": audioOutputConfig,
                    "toolUseOutputConfiguration": {
                        "mediaType": "application/json"
                    },
                    "toolConfiguration": toolConfig
                }
            }
        };
    }
  
    /**
     * Create a contentStartText event
     * @param {string} promptName - Prompt name
     * @param {string} contentName - Content name
     * @param {string} role - Role (SYSTEM, USER, ASSISTANT)
     * @returns {Object} - contentStartText event
     */
    static contentStartText(promptName, contentName, role="SYSTEM") {
        return {
            "event": {
                "contentStart": {
                    "promptName": promptName,
                    "contentName": contentName,
                    "type": "TEXT",
                    "interactive": true,
                    "role": role,
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        };
    }
  
    /**
     * Create a textInput event
     * @param {string} promptName - Prompt name
     * @param {string} contentName - Content name
     * @param {string} systemPrompt - System prompt
     * @returns {Object} - textInput event
     */
    static textInput(promptName, contentName, systemPrompt = S2sEvent.DEFAULT_SYSTEM_PROMPT) {
        return {
            "event": {
                "textInput": {
                    "promptName": promptName,
                    "contentName": contentName,
                    "content": systemPrompt
                }
            }
        };
    }
  
    /**
     * Create a contentEnd event
     * @param {string} promptName - Prompt name
     * @param {string} contentName - Content name
     * @returns {Object} - contentEnd event
     */
    static contentEnd(promptName, contentName) {
        return {
            "event": {
                "contentEnd": {
                    "promptName": promptName,
                    "contentName": contentName
                }
            }
        };
    }
  
    /**
     * Create a contentStartAudio event
     * @param {string} promptName - Prompt name
     * @param {string} contentName - Content name
     * @param {Object} audioInputConfig - Audio input configuration
     * @returns {Object} - contentStartAudio event
     */
    static contentStartAudio(promptName, contentName, audioInputConfig = S2sEvent.DEFAULT_AUDIO_INPUT_CONFIG) {
        return {
            "event": {
                "contentStart": {
                    "promptName": promptName,
                    "contentName": contentName,
                    "type": "AUDIO",
                    "interactive": true,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 16000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64"
                    }
                }
            }
        };
    }
  
    /**
     * Create an audioInput event
     * @param {string} promptName - Prompt name
     * @param {string} contentName - Content name
     * @param {string} content - Base64 encoded audio content
     * @returns {Object} - audioInput event
     */
    static audioInput(promptName, contentName, content) {
        return {
            event: {
                audioInput: {
                    promptName,
                    contentName,
                    content,
                }
            }
        };
    }
  
    /**
     * Create a promptEnd event
     * @param {string} promptName - Prompt name
     * @returns {Object} - promptEnd event
     */
    static promptEnd(promptName) {
        return {
            event: {
                promptEnd: {
                    promptName
                }
            }
        };
    }
  
    /**
     * Create a sessionEnd event
     * @returns {Object} - sessionEnd event
     */
    static sessionEnd() {
        return { event: { sessionEnd: {} } };
    }
}

export default S2sEvent;