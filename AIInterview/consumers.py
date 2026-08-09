import json
import base64
import os
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from AIrounds.models import CandidateInterviewLink, InterviewQuestion, InterviewRound
from AIrounds.services.ai_base import AIBaseService
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    AudioEchoCancellation,
    AudioNoiseReduction,
    AzureStandardVoice,
    InputAudioFormat,
    Modality,
    OutputAudioFormat,
    RequestSession,
    ServerEventType,
    ServerVad
)


class AzureVoiceLiveConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that acts as a secure backend proxy to Azure VoiceLive.
    Relays PCM16 audio bytes and event JSONs between browser and Azure VoiceLive.
    """

    def resolve_agent_settings(self):
        try:
            link = CandidateInterviewLink.objects.select_related(
                "session", "session__application__job"
            ).get(token=self.exam_token)
            company = link.session.application.job.company if (link.session.application and link.session.application.job) else None
            model_name = AIBaseService.get_model_for_company(company)
        except Exception:
            model_name = "Kimi-K2.6"
            
        def clean_endpoint(url):
            if not url:
                return ""
            url = url.strip()
            if url.endswith("/openai/v1/"):
                url = url[:-11]
            elif url.endswith("/openai/v1"):
                url = url[:-10]
            if not url.endswith("/"):
                url += "/"
            return url

        # Default fallback is Kimi (Since KIMI_API_KEY is available)
        api_key = os.environ.get("KIMI_API_KEY", "")
        endpoint = clean_endpoint(os.environ.get("AZURE_KIMI_ENDPOINT", "https://lakkavaramlinus-6415-resource.services.ai.azure.com/"))
        model = os.environ.get("AZURE_KIMI_DEPLOYMENT", "Kimi-K2.6")
        
        # If settings select grok
        if model_name in ("grok", "grok-4-20-non-reasoning", "grok-4.20-non-reasoning", "grok-4-1-fast-non-reasoning", "grok-4.1-non-reasoning"):
            api_key = os.environ.get("GROK_API_KEY", os.environ.get("KIMI_API_KEY", ""))
            endpoint = clean_endpoint(os.environ.get("AZURE_GROK_ENDPOINT", "https://lakkavaramlinus-1936-resource.services.ai.azure.com/"))
            model = os.environ.get("AZURE_GROK_DEPLOYMENT", "grok-4-20-non-reasoning")
        elif model_name in ("kimi", "Kimi-K2.6"):
            api_key = os.environ.get("KIMI_API_KEY", "")
            endpoint = clean_endpoint(os.environ.get("AZURE_KIMI_ENDPOINT", "https://lakkavaramlinus-6415-resource.services.ai.azure.com/"))
            model = os.environ.get("AZURE_KIMI_DEPLOYMENT", "Kimi-K2.6")
            
        return api_key, endpoint, model

    async def connect(self):
        self.exam_token = self.scope['url_route']['kwargs']['exam_token']
        self.round_id = self.scope['url_route']['kwargs']['round_id']
        
        # Dynamically resolve settings/credentials based on AgentSettings (selected model)
        api_key, endpoint, model = await asyncio.get_event_loop().run_in_executor(
            None, self.resolve_agent_settings
        )
        
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.voice_name = "en-US-Ava:DragonHDLatestNeural"
        
        if not self.api_key:
            logging.error("Azure VoiceLive API key is not configured.")
            await self.close()
            return
            
        await self.accept()
        
        # Start connection task to Azure VoiceLive
        self.azure_task = asyncio.create_task(self.connect_to_azure())

    async def disconnect(self, close_code):
        if hasattr(self, 'azure_task'):
            self.azure_task.cancel()
        if hasattr(self, 'azure_conn') and self.azure_conn:
            try:
                await self.azure_conn.close()
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        if not hasattr(self, 'azure_conn') or not self.azure_conn:
            return
            
        if bytes_data:
            # Relay binary PCM16 audio to Azure VoiceLive
            try:
                audio_base64 = base64.b64encode(bytes_data).decode("utf-8")
                await self.azure_conn.input_audio_buffer.append(audio=audio_base64)
            except Exception as e:
                logging.error(f"Error sending audio to Azure: {e}")
        elif text_data:
            # Handle text messages if sent by browser
            try:
                data = json.loads(text_data)
                # E.g. manual text message or interrupt signal
                if data.get("type") == "cancel":
                    await self.azure_conn.response.cancel()
                elif data.get("type") == "InjectUserMessage":
                    message_text = data.get("message")
                    if message_text:
                        from azure.ai.voicelive.models import UserMessageItem, InputTextContentPart
                        item = UserMessageItem(
                            content=[
                                InputTextContentPart(text=message_text)
                            ]
                        )
                        await self.azure_conn.conversation.item.create(item=item)
                        await self.azure_conn.response.create()
            except Exception as e:
                logging.error(f"Error handling text from browser: {e}")

    async def connect_to_azure(self):
        try:
            # Build system prompt for this interview session
            system_prompt = await asyncio.get_event_loop().run_in_executor(
                None, self.get_interview_prompt
            )
            
            credential = AzureKeyCredential(self.api_key)
            async with connect(
                endpoint=self.endpoint,
                credential=credential,
                model=self.model,
            ) as connection:
                self.azure_conn = connection
                
                # Setup session
                voice_config = AzureStandardVoice(name=self.voice_name)
                turn_detection_config = ServerVad(
                    threshold=0.5,
                    prefix_padding_ms=300,
                    silence_duration_ms=800,  # 800ms silence duration to avoid premature cutoffs
                    interrupt_response=True   # Allow candidates to interrupt Sophia naturally
                )
                
                session_config = RequestSession(
                    modalities=[Modality.TEXT, Modality.AUDIO],
                    instructions=system_prompt,
                    voice=voice_config,
                    input_audio_format=InputAudioFormat.PCM16,
                    output_audio_format=OutputAudioFormat.PCM16,
                    turn_detection=turn_detection_config,
                    input_audio_echo_cancellation=AudioEchoCancellation(),
                    input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
                )
                await connection.session.update(session=session_config)
                
                # Trigger the initial greeting/welcome response
                await connection.response.create()
                
                # Process incoming server events
                async for event in connection:
                    await self.handle_azure_event(event)
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error in Azure VoiceLive loop: {e}")
            await self.send(text_data=json.dumps({"type": "Error", "message": str(e)}))
            await self.close()

    def get_interview_prompt(self):
        try:
            link = CandidateInterviewLink.objects.select_related(
                "session", "session__candidate"
            ).get(token=self.exam_token)
            
            try:
                round_obj = link.session.rounds.get(id=self.round_id)
                round_designation = round_obj.get_designation_display() or round_obj.designation
                difficulty = round_obj.difficulty or "MID"
                max_questions = round_obj.max_questions or 10
                programming_language = round_obj.programming_language or ""
            except InterviewRound.DoesNotExist:
                round_designation = "Interview"
                difficulty = "MID"
                max_questions = 10
                programming_language = ""

            job_title = link.session.job_title or "the position"
            candidate_name = f"{link.session.candidate.first_name} {link.session.candidate.last_name}" if link.session.candidate else "Candidate"
            
            prompt = f"""You are Sophia, an elite AI HR Interview Agent conducting a live voice interview for the position of "{job_title}".
The candidate's name is {candidate_name}.

INTERVIEW CONTEXT:
- Round Type: {round_designation}
- Difficulty Level: {difficulty}
- Target Number of Questions: {max_questions}
"""
            if programming_language:
                prompt += f"- Programming Language Focus: {programming_language}\n"
            if link.session.job_description:
                jd_trimmed = link.session.job_description[:500] + "..." if len(link.session.job_description) > 500 else link.session.job_description
                prompt += f"- Job Description: {jd_trimmed}\n"
            if link.session.candidate_skills:
                prompt += f"- Candidate Skills: {link.session.candidate_skills}\n"

            prompt += f"""
OBJECTIVES:
1. Conduct a structured, professional, and friendly verbal screening for the "{round_designation}" round.
2. Ask questions relevant to the round context and difficulty ({difficulty}).
3. Guide the candidate through questions one by one. Do not ask double-barreled or multiple questions at the same time.

STYLE & BEHAVIOR (CRITICAL FOR A NATURAL, HUMAN VOICE AGENT):
- Speak naturally like a real human. Use warm, professional spoken English.
- Use natural spoken transitions and active listening acknowledgments. Start your turn with brief phrases like "Got it", "Interesting point", "Makes sense", "Thanks for sharing that", or "Excellent" where appropriate before responding or asking the next question.
- Keep your responses very brief and conversational (maximum 2-3 sentences). Remember, this is a spoken voice call, not a text chat.
- Adjust the depth of your questions based on the candidate's answers. If they are brief, ask a follow-up ("Could you elaborate on how you handled...?", "What was the biggest challenge there?").
- Do NOT output bullet points, numbered lists, markdown formatting, or emojis. Speak in fluid, complete sentences.
- Never break character. You are Sophia, the interviewer. Never mention you are an AI model or mention backend settings.

ROUND-SPECIFIC SCREENING FOCUS:
- For TECHNICAL rounds: Evaluate test frameworks, system architecture, scalability, API design, and debugging.
- For HR/CULTURAL FIT rounds: Assess communication, collaboration, adaptability, career alignment, and teamwork.
- For CODING rounds: Focus on problem-solving approach, algorithms, data structures, complexity (Big O), and {programming_language} if specified.
- For BEHAVIORAL rounds: Ask situational questions, and use the STAR method to probe past experiences.

Now, welcome {candidate_name} warmly to the {round_designation} round, briefly introduce yourself as Sophia the AI interviewer, and ask the first question to begin the interview.
"""
            return prompt
        except Exception as e:
            logging.error(f"Error getting interview prompt: {e}")
            return "You are Sophia, a helpful AI HR Interviewer. Respond naturally and conversationally."

    async def handle_azure_event(self, event):
        try:
            if event.type == ServerEventType.SESSION_UPDATED:
                logging.info("Azure VoiceLive session updated successfully.")
                await self.send(text_data=json.dumps({"type": "SettingsApplied"}))
            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                await self.send(text_data=json.dumps({"type": "UserStartedSpeaking"}))
            elif event.type == ServerEventType.RESPONSE_CREATED:
                await self.send(text_data=json.dumps({"type": "AgentStartedSpeaking"}))
            elif event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                # Azure VoiceLive SDK returns event.delta as a base64-encoded string.
                # Decode to raw PCM16 bytes before sending as binary to the browser.
                try:
                    audio_bytes = base64.b64decode(event.delta)
                    await self.send(bytes_data=audio_bytes)
                except Exception as audio_err:
                    logging.error(f"Failed to decode/send audio delta: {audio_err}")
            elif event.type == ServerEventType.RESPONSE_AUDIO_DONE:
                await self.send(text_data=json.dumps({"type": "AgentAudioDone"}))
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                delta_text = getattr(event, 'delta', '') or ''
                await self.send(text_data=json.dumps({"type": "AgentTranscriptDelta", "delta": delta_text}))
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE:
                transcript_text = getattr(event, 'transcript', '') or ''
                await self.send(text_data=json.dumps({"type": "AgentTranscriptDone", "transcript": transcript_text}))
            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_DELTA:
                delta_text = getattr(event, 'delta', '') or ''
                await self.send(text_data=json.dumps({"type": "UserTranscriptDelta", "delta": delta_text}))
            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                transcript_text = getattr(event, 'transcript', '') or ''
                await self.send(text_data=json.dumps({"type": "UserTranscriptDone", "transcript": transcript_text}))
            elif event.type == ServerEventType.ERROR:
                error_msg = getattr(event, 'error', None)
                message = error_msg.message if error_msg and hasattr(error_msg, 'message') else str(error_msg or 'Unknown error')
                logging.error(f"Azure VoiceLive error event: {message}")
                await self.send(text_data=json.dumps({"type": "Error", "message": message}))
        except Exception as e:
            logging.error(f"Error handling event {getattr(event, 'type', 'unknown')}: {e}")


class WebRTCSignalingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for WebRTC peer-to-peer signaling.

    Handles SDP offer/answer exchange and ICE candidate relay between
    participants in the same interview room. The room is identified by
    a unique session ID (UUID) that is only known to authorized participants.

    Protocol messages (JSON):
      → { "type": "offer",     "sdp": "..." }
      → { "type": "answer",    "sdp": "..." }
      → { "type": "ice",       "candidate": {...} }
      → { "type": "join",      "displayName": "..." }
      → { "type": "leave" }

    All messages are relayed to ALL other peers in the same room group.
    """

    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'webrtc_{self.room_id}'

        # Join the room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Notify other peers that someone joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'relay_message',
                'message': json.dumps({'type': 'peer_joined'}),
                'sender_channel': self.channel_name,
            }
        )

    async def disconnect(self, close_code):
        # Notify other peers that someone left
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'relay_message',
                'message': json.dumps({'type': 'peer_left'}),
                'sender_channel': self.channel_name,
            }
        )

        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        """Receive a signaling message and relay it to all other peers."""
        # Validate JSON
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', '')

        # Only relay recognized signaling message types
        if msg_type not in ('offer', 'answer', 'ice', 'join', 'leave'):
            return

        # Broadcast to all other peers in the room (exclude sender)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'relay_message',
                'message': text_data,
                'sender_channel': self.channel_name,
            }
        )

    async def relay_message(self, event):
        """Forward a signaling message to this WebSocket, but skip if we are the sender."""
        if event.get('sender_channel') == self.channel_name:
            return

        await self.send(text_data=event['message'])
