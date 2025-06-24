import json

class S2sEvent:
  # Default configuration values
  DEFAULT_INFER_CONFIG = {
        "maxTokens": 1024,
        "topP": 0.95,
        "temperature": 0.7
    }
  #DEFAULT_SYSTEM_PROMPT = "You are a friend. The user and you will engage in a spoken dialog " \
  #            "exchanging the transcripts of a natural real-time conversation. Keep your responses short, " \
  #            "generally two or three sentences for chatty scenarios."
  DEFAULT_SYSTEM_PROMPT = """You are a professional AI Interviewer specializing in technical job interviews. Your role is to assess candidate qualifications through thoughtful, relevant questions.
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

  DEFAULT_AUDIO_INPUT_CONFIG = {
        "mediaType":"audio/lpcm",
        "sampleRateHertz":16000,
        "sampleSizeBits":16,
        "channelCount":1,
        "audioType":"SPEECH","encoding":"base64"
      }
  DEFAULT_AUDIO_OUTPUT_CONFIG = {
          "mediaType": "audio/lpcm",
          "sampleRateHertz": 24000,
          "sampleSizeBits": 16,
          "channelCount": 1,
          "voiceId": "tiffany",
          "encoding": "base64",
          "audioType": "SPEECH"
        }
  
  getInterviewQuestion_schema = json.dumps({
        "type": "object",
        "properties": {
            "job_title": {
                "type": "string",
                "description": "The job position title to get interview questions for. Supported job titles are Data Science, Java developer, and AI Consultant",
                "default": "Data Science"
            }
        },
        "required": ["job_title"]
      }) 

  DEFAULT_TOOL_CONFIG = {
          "tools": [
              {
                  "toolSpec": {
                      "name": "getDateTool",
                      "description": "get information about the current day",
                      "inputSchema": {
                          "json": '''{
                            "$schema": "http://json-schema.org/draft-07/schema#",
                            "type": "object",
                            "properties": {},
                            "required": []
                        }'''
                      }
                  }
              },
              {
                  "toolSpec": {
                      "name": "getInterviewQuestion",
                      "description": "Get a specific interview question for a job position. Each call returns the next question in sequence.",
                      "inputSchema": {
                          "json": getInterviewQuestion_schema
                      }
                  }
              }
          ]
        }
  
  @staticmethod
  def session_start(inference_config=DEFAULT_INFER_CONFIG): 
    return {"event":{"sessionStart":{"inferenceConfiguration":inference_config}}}

  @staticmethod
  def prompt_start(prompt_name, 
                   audio_output_config=DEFAULT_AUDIO_OUTPUT_CONFIG, 
                   tool_config=DEFAULT_TOOL_CONFIG):
    return {
          "event": {
            "promptStart": {
              "promptName": prompt_name,
              "textOutputConfiguration": {
                "mediaType": "text/plain"
              },
              "audioOutputConfiguration": audio_output_config,
              "toolUseOutputConfiguration": {
                "mediaType": "application/json"
              },
              "toolConfiguration": tool_config
            }
          }
        }

  @staticmethod
  def content_start_text(prompt_name, content_name, role="SYSTEM"):
    return {
        "event":{
        "contentStart":{
          "promptName":prompt_name,
          "contentName":content_name,
          "type":"TEXT",
          "interactive":True,
          "role": role,
          "textInputConfiguration":{
            "mediaType":"text/plain"
            }
          }
        }
      }
    
  @staticmethod
  def text_input(prompt_name, content_name, system_prompt=DEFAULT_SYSTEM_PROMPT):
    return {
      "event":{
        "textInput":{
          "promptName":prompt_name,
          "contentName":content_name,
          "content":system_prompt,
        }
      }
    }
  
  @staticmethod
  def content_end(prompt_name, content_name):
    return {
      "event":{
        "contentEnd":{
          "promptName":prompt_name,
          "contentName":content_name
        }
      }
    }

  @staticmethod
  def content_start_audio(prompt_name, content_name, audio_input_config=DEFAULT_AUDIO_INPUT_CONFIG):
    return {
      "event":{
        "contentStart":{
          "promptName":prompt_name,
          "contentName":content_name,
          "type":"AUDIO",
          "interactive":True,
          "role": "USER",
          "audioInputConfiguration":audio_input_config
        }
      }
    }
    
  @staticmethod
  def audio_input(prompt_name, content_name, content):
    return {
      "event": {
        "audioInput": {
          "promptName": prompt_name,
          "contentName": content_name,
          "content": content,
        }
      }
    }
  
  @staticmethod
  def content_start_tool(prompt_name, content_name, tool_use_id):
    return {
        "event": {
          "contentStart": {
            "promptName": prompt_name,
            "contentName": content_name,
            "interactive": False,
            "type": "TOOL",
            "role": "TOOL",
            "toolResultInputConfiguration": {
              "toolUseId": tool_use_id,
              "type": "TEXT",
              "textInputConfiguration": {
                "mediaType": "text/plain"
              }
            }
          }
        }
      }
  
  @staticmethod
  def text_input_tool(prompt_name, content_name, content):
    return {
      "event": {
        "toolResult": {
          "promptName": prompt_name,
          "contentName": content_name,
          "content": content,
          # "role": "TOOL"
        }
      }
    }
  
  @staticmethod
  def prompt_end(prompt_name):
    return {
      "event": {
        "promptEnd": {
          "promptName": prompt_name
        }
      }
    }
  
  @staticmethod
  def session_end():
    return  {
      "event": {
        "sessionEnd": {}
      }
    }
