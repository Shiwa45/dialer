"""
sarvam/ai_conversation_engine.py – Phase 8.1: Conversation Engine
===================================================================

Manages conversation flow, generates responses, tracks context.
Uses Sarvam TTS for speech output.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from sarvam.intent_detector import get_intent_detector
from sarvam.tts_service import get_tts

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Stores conversation state and history."""
    call_id: int
    language: str = 'hi-IN'
    turn_count: int = 0
    max_turns: int = 15
    conversation_history: List[Dict] = field(default_factory=list)
    collected_data: Dict = field(default_factory=dict)
    current_intent: Optional[str] = None
    awaiting_confirmation: bool = False
    confirmation_data: Optional[Dict] = None
    
    def add_turn(self, role: str, text: str, intent: str = None):
        """Add a conversation turn."""
        self.conversation_history.append({
            'role': role,
            'text': text,
            'intent': intent,
            'timestamp': datetime.now().isoformat(),
        })
        self.turn_count += 1
    
    def is_complete(self) -> bool:
        """Check if conversation should end."""
        return self.turn_count >= self.max_turns
    
    def get_last_user_message(self) -> Optional[str]:
        """Get last message from user."""
        for msg in reversed(self.conversation_history):
            if msg['role'] == 'user':
                return msg['text']
        return None


class AIConversationEngine:
    """
    AI Conversation Engine for Sarvam-based agents.
    
    Features:
    - Intent-based responses
    - Context tracking
    - Entity collection (for appointments, etc.)
    - Multi-turn conversations
    - Action execution
    """
    
    def __init__(
        self,
        language: str = 'hi-IN',
        agent_name: str = 'AI सहायक',
        company_name: str = 'आपकी कंपनी',
    ):
        self.language = language
        self.agent_name = agent_name
        self.company_name = company_name
        self.intent_detector = get_intent_detector(language)
        self.tts = get_tts()
    
    def process_turn(
        self,
        customer_text: str,
        context: ConversationContext,
    ) -> Dict:
        """
        Process one conversation turn.
        
        Args:
            customer_text: What customer said (from ASR)
            context: Current conversation context
        
        Returns:
            {
                'response_text': 'जी बिल्कुल! किस तारीख के लिए?',
                'response_audio': '/path/to/audio.wav',
                'intent': 'book_appointment',
                'action': {'action': 'book_appointment', ...},
                'end_call': False,
            }
        """
        
        # Add customer message to context
        context.add_turn('user', customer_text)
        
        # Detect intent
        intent_result = self.intent_detector.detect(customer_text)
        intent = intent_result['intent']
        entities = intent_result.get('entities', {})
        
        context.current_intent = intent
        
        logger.info(f"Call {context.call_id} Turn {context.turn_count}: "
                   f"Intent={intent}, Entities={entities}")
        
        # Handle confirmation flow
        if context.awaiting_confirmation:
            return self._handle_confirmation(
                customer_text, intent, context
            )
        
        # Generate response based on intent
        response_data = self._generate_response(
            intent, entities, context
        )
        
        # Add AI response to context
        context.add_turn('assistant', response_data['text'], intent)
        
        # Generate audio
        audio_path = self.tts.generate(
            text=response_data['text'],
            language=self.language,
            voice='aditya',  # Use first available voice
            output_name=f'ai_response_{context.call_id}_{context.turn_count}'
        )
        
        return {
            'response_text': response_data['text'],
            'response_audio': audio_path,
            'intent': intent,
            'action': response_data.get('action'),
            'end_call': response_data.get('end_call', False),
        }
    
    def _generate_response(
        self,
        intent: str,
        entities: Dict,
        context: ConversationContext,
    ) -> Dict:
        """Generate appropriate response for intent."""
        
        templates = self._get_response_templates()
        
        if intent == 'book_appointment':
            return self._handle_appointment_booking(entities, context)
        
        elif intent == 'cancel_appointment':
            return self._handle_appointment_cancel(entities, context)
        
        elif intent == 'product_inquiry':
            return {
                'text': templates['product_inquiry'],
                'action': None,
            }
        
        elif intent == 'pricing_inquiry':
            return {
                'text': templates['pricing_inquiry'],
                'action': None,
            }
        
        elif intent == 'complaint':
            return {
                'text': templates['complaint'],
                'action': {'action': 'log_complaint'},
            }
        
        elif intent == 'transfer_human':
            return {
                'text': templates['transfer_human'],
                'action': {'action': 'transfer_to_human'},
                'end_call': True,
            }
        
        elif intent == 'greeting':
            return {
                'text': templates['greeting'],
                'action': None,
            }
        
        elif intent == 'goodbye':
            return {
                'text': templates['goodbye'],
                'action': None,
                'end_call': True,
            }
        
        else:  # unknown
            return {
                'text': templates['fallback'],
                'action': None,
            }
    
    def _handle_appointment_booking(
        self,
        entities: Dict,
        context: ConversationContext,
    ) -> Dict:
        """Multi-step appointment booking flow."""
        
        # Collect required data
        required_fields = ['date', 'time']
        
        # Store entities
        context.collected_data.update(entities)
        
        # Check what's missing
        missing = [f for f in required_fields 
                  if f not in context.collected_data]
        
        if missing:
            # Ask for missing information
            if 'date' in missing:
                return {
                    'text': self._get_text('ask_appointment_date'),
                    'action': None,
                }
            elif 'time' in missing:
                return {
                    'text': self._get_text('ask_appointment_time'),
                    'action': None,
                }
        
        # All data collected - confirm
        context.awaiting_confirmation = True
        context.confirmation_data = {
            'type': 'book_appointment',
            'date': context.collected_data.get('date'),
            'time': context.collected_data.get('time'),
        }
        
        return {
            'text': self._get_text('confirm_appointment').format(
                date=context.collected_data.get('date', 'उस दिन'),
                time=context.collected_data.get('time', 'उस समय')
            ),
            'action': None,
        }
    
    def _handle_appointment_cancel(
        self,
        entities: Dict,
        context: ConversationContext,
    ) -> Dict:
        """Handle appointment cancellation."""
        
        context.awaiting_confirmation = True
        context.confirmation_data = {'type': 'cancel_appointment'}
        
        return {
            'text': self._get_text('confirm_cancel'),
            'action': None,
        }
    
    def _handle_confirmation(
        self,
        customer_text: str,
        intent: str,
        context: ConversationContext,
    ) -> Dict:
        """Handle yes/no confirmation."""
        
        if intent == 'confirm_yes':
            # Execute the action
            conf_data = context.confirmation_data
            
            if conf_data['type'] == 'book_appointment':
                action = {
                    'action': 'book_appointment',
                    'date': conf_data.get('date'),
                    'time': conf_data.get('time'),
                }
                response_text = self._get_text('appointment_booked')
            
            elif conf_data['type'] == 'cancel_appointment':
                action = {'action': 'cancel_appointment'}
                response_text = self._get_text('appointment_cancelled')
            
            else:
                action = None
                response_text = self._get_text('confirmed')
            
            context.awaiting_confirmation = False
            context.confirmation_data = None
            
            return {
                'text': response_text,
                'action': action,
            }
        
        elif intent == 'confirm_no':
            context.awaiting_confirmation = False
            context.confirmation_data = None
            context.collected_data.clear()
            
            return {
                'text': self._get_text('cancelled_action'),
                'action': None,
            }
        
        else:
            # Customer said something else
            return {
                'text': self._get_text('please_confirm'),
                'action': None,
            }
    
    def _get_response_templates(self) -> Dict[str, str]:
        """Get response templates for language."""
        
        if self.language == 'hi-IN':
            return {
                'greeting': f'नमस्ते! मैं {self.agent_name} हूं। मैं आपकी कैसे मदद कर सकता हूं?',
                'product_inquiry': 'जी बिल्कुल! मैं आपको हमारे प्रोडक्ट्स के बारे में बताता हूं। आपको किस प्रोडक्ट की जानकारी चाहिए?',
                'pricing_inquiry': 'हमारी प्राइसिंग की जानकारी के लिए मैं आपको एक एजेंट से जोड़ता हूं।',
                'complaint': 'मुझे खेद है कि आपको समस्या हुई। कृपया विस्तार से बताएं क्या परेशानी है?',
                'transfer_human': 'ठीक है, मैं आपको एक एजेंट से जोड़ता हूं। कृपया एक मिनट रुकें।',
                'goodbye': 'धन्यवाद! अच्छा दिन हो।',
                'fallback': 'क्षमा करें, मुझे समझने में दिक्कत हो रही है। क्या आप फिर से बता सकते हैं?',
                'ask_appointment_date': 'जी बिल्कुल! किस तारीख के लिए अपॉइंटमेंट चाहिए?',
                'ask_appointment_time': 'ठीक है! कौनसा समय सही रहेगा - सुबह या शाम?',
                'confirm_appointment': 'ठीक है, मैं {date} को {time} के लिए अपॉइंटमेंट बुक कर देता हूं। कन्फर्म करें?',
                'confirm_cancel': 'आप अपना अपॉइंटमेंट कैंसल करना चाहते हैं। कन्फर्म करें?',
                'appointment_booked': 'परफेक्ट! आपका अपॉइंटमेंट बुक हो गया। SMS से कन्फर्मेशन मिलेगा।',
                'appointment_cancelled': 'ठीक है, अपॉइंटमेंट कैंसल कर दिया गया।',
                'confirmed': 'ठीक है, हो गया!',
                'cancelled_action': 'ठीक है, कोई बात नहीं। और कुछ मदद चाहिए?',
                'please_confirm': 'कृपया हां या ना में जवाब दें।',
            }
        
        else:  # en-IN
            return {
                'greeting': f'Hello! I am {self.agent_name}. How can I help you today?',
                'product_inquiry': 'Sure! I can help you with product information. Which product are you interested in?',
                'pricing_inquiry': 'For pricing information, let me connect you to an agent.',
                'complaint': 'I apologize for the inconvenience. Could you please tell me what happened?',
                'transfer_human': 'Sure, let me connect you to an agent. Please hold for a moment.',
                'goodbye': 'Thank you! Have a great day.',
                'fallback': 'Sorry, I did not quite understand. Could you please repeat that?',
                'ask_appointment_date': 'Sure! Which date works for you?',
                'ask_appointment_time': 'Great! What time would be convenient - morning or evening?',
                'confirm_appointment': 'Okay, I will book your appointment for {date} at {time}. Confirm?',
                'confirm_cancel': 'You want to cancel your appointment. Confirm?',
                'appointment_booked': 'Perfect! Your appointment is booked. You will receive an SMS confirmation.',
                'appointment_cancelled': 'Okay, your appointment has been cancelled.',
                'confirmed': 'Done!',
                'cancelled_action': 'No problem. Anything else I can help with?',
                'please_confirm': 'Please answer yes or no.',
            }
    
    def _get_text(self, key: str) -> str:
        """Get template text for key."""
        templates = self._get_response_templates()
        return templates.get(key, templates['fallback'])


def create_conversation_context(call_id: int, language: str = 'hi-IN') -> ConversationContext:
    """Create new conversation context for a call."""
    return ConversationContext(
        call_id=call_id,
        language=language,
    )
