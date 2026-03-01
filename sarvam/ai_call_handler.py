"""
sarvam/ai_call_handler.py – Phase 8.2: AI Call Handler
========================================================

Manages real-time AI-powered calls via Asterisk ARI.

Flow:
1. Call starts → Play greeting
2. Record customer speech (3-10 seconds with silence detection)
3. Transcribe to text (Sarvam ASR)
4. Process with AI engine (intent + response)
5. Generate response audio (Sarvam TTS)
6. Play to customer
7. Execute any actions (book appointment, transfer, etc.)
8. Loop until call ends or max turns reached
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from sarvam.asr_service import get_asr
from sarvam.ai_conversation_engine import (
    AIConversationEngine,
    create_conversation_context,
)
from sarvam.action_executor import get_action_executor
from sarvam.tts_service import get_tts

logger = logging.getLogger(__name__)


class AICallHandler:
    """
    Handles real-time AI-powered calls via Asterisk ARI.
    
    Integrates with your existing ARI infrastructure.
    """
    
    def __init__(
        self,
        asterisk_service,
        channel_id: str,
        call_log,
        lead=None,
        language: str = 'hi-IN',
        agent_name: str = 'AI सहायक',
        company_name: str = 'आपकी कंपनी',
    ):
        self.asterisk = asterisk_service
        self.channel_id = channel_id
        self.call_log = call_log
        self.lead = lead
        self.language = language
        
        # Services
        self.asr = get_asr()
        self.tts = get_tts()
        self.ai_engine = AIConversationEngine(
            language=language,
            agent_name=agent_name,
            company_name=company_name,
        )
        self.action_executor = get_action_executor()
        
        # Conversation state
        self.context = create_conversation_context(
            call_id=call_log.id,
            language=language,
        )
        
        # Call state
        self.is_active = True
        self.recording_dir = Path('/tmp/ai_recordings')
        self.recording_dir.mkdir(parents=True, exist_ok=True)
    
    async def start(self):
        """
        Start AI conversation loop.
        
        This is the main entry point called by ARI worker.
        """
        logger.info(f"AI call handler started: call={self.call_log.id}, "
                   f"channel={self.channel_id}, lang={self.language}")
        
        try:
            # Answer the call
            await self._answer_call()
            
            # Play greeting
            await self._play_greeting()
            
            # Main conversation loop
            while self.is_active and not self.context.is_complete():
                # 1. Record customer speech
                audio_file = await self._record_customer_speech()
                if not audio_file:
                    logger.warning("No audio recorded, ending call")
                    break
                
                # 2. Transcribe
                transcription = self.asr.transcribe(
                    audio_file_path=audio_file,
                    language_code=self.language,
                )
                
                customer_text = transcription.get('text', '').strip()
                
                if not customer_text:
                    logger.warning("Empty transcription")
                    await self._play_error_message()
                    continue
                
                logger.info(f"Customer said: {customer_text}")
                
                # 3. Process with AI
                ai_result = self.ai_engine.process_turn(
                    customer_text=customer_text,
                    context=self.context,
                )
                
                logger.info(f"AI response: {ai_result['response_text']}")
                
                # 4. Play response
                if ai_result['response_audio']:
                    await self._play_audio(ai_result['response_audio'])
                
                # 5. Execute action if any
                if ai_result.get('action'):
                    action_result = self.action_executor.execute(
                        action=ai_result['action'],
                        call_log=self.call_log,
                        lead=self.lead,
                    )
                    
                    logger.info(f"Action result: {action_result}")
                    
                    # Check if transfer requested
                    if action_result.get('transfer'):
                        await self._transfer_to_human()
                        break
                
                # 6. Check if call should end
                if ai_result.get('end_call'):
                    logger.info("AI requested call end")
                    break
            
            # Play goodbye
            await self._play_goodbye()
            
            # Update call log
            self._finalize_call()
            
        except Exception as e:
            logger.error(f"AI call handler error: {e}", exc_info=True)
        finally:
            # Hangup
            try:
                await self._hangup()
            except Exception:
                pass
    
    async def _answer_call(self):
        """Answer the call."""
        try:
            self.asterisk.answer_channel(self.channel_id)
            await asyncio.sleep(0.5)  # Give time for answer
        except Exception as e:
            logger.error(f"Answer error: {e}")
    
    async def _play_greeting(self):
        """Play initial greeting."""
        greetings = {
            'hi-IN': 'नमस्ते! मैं आपकी AI सहायक हूं। मैं आपकी कैसे मदद कर सकती हूं?',
            'en-IN': 'Hello! I am your AI assistant. How can I help you today?',
            'ta-IN': 'வணக்கம்! நான் உங்கள் AI உதவியாளர். உங்களுக்கு எப்படி உதவ முடியும்?',
        }
        
        greeting_text = greetings.get(self.language, greetings['en-IN'])
        
        # Generate greeting audio
        greeting_audio = self.tts.generate(
            text=greeting_text,
            language=self.language,
            voice='aditya',
            output_name=f'greeting_{self.call_log.id}',
        )
        
        if greeting_audio:
            await self._play_audio(greeting_audio)
    
    async def _record_customer_speech(self) -> Optional[str]:
        """
        Record customer speech with silence detection.
        
        Returns:
            Path to recorded audio file
        """
        try:
            recording_name = f'customer_{self.call_log.id}_{self.context.turn_count}'
            recording_path = str(self.recording_dir / f'{recording_name}.wav')
            
            # Start recording with silence detection
            # Using Asterisk Record application via ARI
            self.asterisk.record_channel(
                channel_id=self.channel_id,
                name=recording_name,
                format='wav',
                max_duration_seconds=10,
                max_silence_seconds=2,
                beep=False,
                if_exists='overwrite',
            )
            
            # Wait for recording to complete
            # In production, listen for RecordingFinished event
            await asyncio.sleep(12)  # Max duration + buffer
            
            # Check if file exists
            if Path(recording_path).exists():
                return recording_path
            
            logger.warning(f"Recording file not found: {recording_path}")
            return None
        
        except Exception as e:
            logger.error(f"Recording error: {e}")
            return None
    
    async def _play_audio(self, audio_path: str):
        """Play audio file to customer."""
        try:
            if not Path(audio_path).exists():
                logger.error(f"Audio file not found: {audio_path}")
                return
            
            # Play audio using Asterisk Playback
            self.asterisk.play_audio(
                channel_id=self.channel_id,
                media=f'sound:{audio_path}',
            )
            
            # Wait for playback to finish
            # In production, listen for PlaybackFinished event
            # For now, estimate based on file size
            file_size = Path(audio_path).stat().st_size
            duration_estimate = max(2, file_size / 16000)  # Rough estimate
            await asyncio.sleep(duration_estimate)
        
        except Exception as e:
            logger.error(f"Playback error: {e}")
    
    async def _play_error_message(self):
        """Play error message when transcription fails."""
        error_messages = {
            'hi-IN': 'क्षमा करें, मुझे सुनने में समस्या हो रही है। क्या आप फिर से कह सकते हैं?',
            'en-IN': 'Sorry, I did not catch that. Could you please repeat?',
        }
        
        error_text = error_messages.get(self.language, error_messages['en-IN'])
        
        error_audio = self.tts.generate(
            text=error_text,
            language=self.language,
            voice='aditya',
            output_name=f'error_{self.call_log.id}',
        )
        
        if error_audio:
            await self._play_audio(error_audio)
    
    async def _play_goodbye(self):
        """Play goodbye message."""
        goodbye_messages = {
            'hi-IN': 'धन्यवाद! अच्छा दिन हो।',
            'en-IN': 'Thank you! Have a great day.',
        }
        
        goodbye_text = goodbye_messages.get(self.language, goodbye_messages['en-IN'])
        
        goodbye_audio = self.tts.generate(
            text=goodbye_text,
            language=self.language,
            voice='aditya',
            output_name=f'goodbye_{self.call_log.id}',
        )
        
        if goodbye_audio:
            await self._play_audio(goodbye_audio)
    
    async def _transfer_to_human(self):
        """Transfer call to human agent queue."""
        try:
            logger.info(f"Transferring call {self.call_log.id} to human agent")
            
            # Play transfer message
            transfer_messages = {
                'hi-IN': 'मैं आपको एक एजेंट से जोड़ रही हूं। कृपया प्रतीक्षा करें।',
                'en-IN': 'Let me transfer you to an agent. Please wait.',
            }
            
            transfer_text = transfer_messages.get(self.language, transfer_messages['en-IN'])
            transfer_audio = self.tts.generate(
                text=transfer_text,
                language=self.language,
                voice='aditya',
                output_name=f'transfer_{self.call_log.id}',
            )
            
            if transfer_audio:
                await self._play_audio(transfer_audio)
            
            # Send to agent queue via dialplan
            self.asterisk.continue_in_dialplan(
                channel_id=self.channel_id,
                context='transfer-to-agent',
                extension='s',
                priority=1,
            )
            
            self.is_active = False
        
        except Exception as e:
            logger.error(f"Transfer error: {e}")
    
    async def _hangup(self):
        """Hangup the call."""
        try:
            self.asterisk.hangup_channel(self.channel_id)
        except Exception as e:
            logger.debug(f"Hangup error (may be already hung up): {e}")
    
    def _finalize_call(self):
        """Update call log with AI conversation data."""
        try:
            # Save conversation transcript
            self.call_log.ai_conversation_transcript = self.context.conversation_history
            self.call_log.ai_turn_count = self.context.turn_count
            self.call_log.handled_by_ai = True
            
            # Save collected data
            if self.context.collected_data:
                self.call_log.ai_collected_data = self.context.collected_data
            
            # Determine final intent
            if self.context.current_intent:
                self.call_log.ai_final_intent = self.context.current_intent
            
            self.call_log.save()
            
            logger.info(f"Call {self.call_log.id} finalized: "
                       f"{self.context.turn_count} turns, "
                       f"intent={self.context.current_intent}")
        
        except Exception as e:
            logger.error(f"Finalize call error: {e}")
