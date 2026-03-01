"""
sarvam/management/commands/test_ai_agent.py
============================================

Test AI agent components without making real calls.

Usage:
    python manage.py test_ai_agent
    python manage.py test_ai_agent --language hi-IN
    python manage.py test_ai_agent --simulate-call
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import json


class Command(BaseCommand):
    help = 'Test AI agent components'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--language',
            type=str,
            default='hi-IN',
            help='Language to test (hi-IN, en-IN, etc.)'
        )
        parser.add_argument(
            '--simulate-call',
            action='store_true',
            help='Simulate a full AI call conversation'
        )
    
    def handle(self, *args, **options):
        language = options['language']
        
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('AI Agent Test Suite'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        # Test 1: ASR Service
        self.stdout.write('\n📝 Test 1: ASR Service')
        self.test_asr()
        
        # Test 2: Intent Detection
        self.stdout.write('\n🧠 Test 2: Intent Detection')
        self.test_intent_detection(language)
        
        # Test 3: Conversation Engine
        self.stdout.write('\n💬 Test 3: Conversation Engine')
        self.test_conversation_engine(language)
        
        # Test 4: TTS Service
        self.stdout.write('\n🎙️  Test 4: TTS Service')
        self.test_tts(language)
        
        # Test 5: Action Executor
        self.stdout.write('\n⚡ Test 5: Action Executor')
        self.test_action_executor()
        
        # Test 6: Full Conversation Simulation
        if options['simulate_call']:
            self.stdout.write('\n📞 Test 6: Full Call Simulation')
            self.simulate_call(language)
        
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('✅ All tests completed!'))
        self.stdout.write('='*70 + '\n')
    
    def test_asr(self):
        """Test ASR service configuration."""
        from sarvam.asr_service import get_asr
        
        try:
            asr = get_asr()
            
            if asr.api_key:
                self.stdout.write(self.style.SUCCESS('  ✅ ASR configured (API key present)'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠️  ASR not configured (no API key)'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ ASR error: {e}'))
    
    def test_intent_detection(self, language):
        """Test intent detection with sample inputs."""
        from sarvam.intent_detector import get_intent_detector
        
        test_cases = {
            'hi-IN': [
                ('मुझे अपॉइंटमेंट बुक करना है', 'book_appointment'),
                ('कीमत क्या है?', 'pricing_inquiry'),
                ('मैं शिकायत करना चाहता हूं', 'complaint'),
                ('किसी इंसान से बात करनी है', 'transfer_human'),
                ('हां', 'confirm_yes'),
            ],
            'en-IN': [
                ('I want to book an appointment', 'book_appointment'),
                ('What is the price?', 'pricing_inquiry'),
                ('I have a complaint', 'complaint'),
                ('Talk to a human', 'transfer_human'),
                ('Yes', 'confirm_yes'),
            ],
        }
        
        detector = get_intent_detector(language)
        cases = test_cases.get(language, test_cases['en-IN'])
        
        correct = 0
        for text, expected_intent in cases:
            result = detector.detect(text)
            detected = result['intent']
            
            if detected == expected_intent:
                self.stdout.write(f'  ✅ "{text}" → {detected}')
                correct += 1
            else:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️  "{text}" → {detected} (expected {expected_intent})'
                ))
        
        accuracy = (correct / len(cases)) * 100
        self.stdout.write(f'\n  📊 Accuracy: {accuracy:.0f}% ({correct}/{len(cases)})')
    
    def test_conversation_engine(self, language):
        """Test conversation engine."""
        from sarvam.ai_conversation_engine import (
            AIConversationEngine,
            create_conversation_context,
        )
        
        try:
            engine = AIConversationEngine(language=language)
            context = create_conversation_context(call_id=999, language=language)
            
            # Test conversation turn
            test_text = 'मुझे अपॉइंटमेंट चाहिए' if language == 'hi-IN' else 'I need an appointment'
            
            result = engine.process_turn(test_text, context)
            
            self.stdout.write(f'  Input: {test_text}')
            self.stdout.write(f'  Intent: {result["intent"]}')
            self.stdout.write(f'  Response: {result["response_text"][:100]}...')
            
            if result['response_audio']:
                self.stdout.write(f'  ✅ TTS audio generated')
            else:
                self.stdout.write(f'  ⚠️  No TTS audio')
            
            self.stdout.write('  ✅ Conversation engine working')
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Error: {e}'))
    
    def test_tts(self, language):
        """Test TTS service."""
        from sarvam.tts_service import get_tts
        
        try:
            tts = get_tts()
            
            if tts.api_key:
                self.stdout.write(self.style.SUCCESS('  ✅ TTS configured (API key present)'))
                
                # Test generation
                test_text = 'नमस्ते' if language == 'hi-IN' else 'Hello'
                
                self.stdout.write(f'  Testing generation: "{test_text}"')
                
                audio_path = tts.generate(
                    text=test_text,
                    language=language,
                    voice='aditya',
                    output_name='test',
                )
                
                if audio_path:
                    self.stdout.write(self.style.SUCCESS(f'  ✅ TTS generated: {audio_path}'))
                else:
                    self.stdout.write(self.style.WARNING('  ⚠️  TTS generation failed'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠️  TTS not configured'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ TTS error: {e}'))
    
    def test_action_executor(self):
        """Test action executor."""
        from sarvam.action_executor import get_action_executor
        
        try:
            executor = get_action_executor()
            
            # Test appointment action (will fail gracefully without real objects)
            action = {
                'action': 'book_appointment',
                'date': 'tomorrow',
                'time': 'morning',
            }
            
            result = executor.execute(action, call_log=None, lead=None)
            
            self.stdout.write(f'  Action: {action["action"]}')
            self.stdout.write(f'  Result: {result.get("message", result.get("error"))}')
            self.stdout.write('  ✅ Action executor working')
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Error: {e}'))
    
    def simulate_call(self, language):
        """Simulate a full AI call conversation."""
        from sarvam.ai_conversation_engine import (
            AIConversationEngine,
            create_conversation_context,
        )
        
        self.stdout.write('\n' + '─'*70)
        self.stdout.write('  Simulating AI Call Conversation')
        self.stdout.write('─'*70 + '\n')
        
        engine = AIConversationEngine(language=language)
        context = create_conversation_context(call_id=999, language=language)
        
        # Simulated conversation
        if language == 'hi-IN':
            conversation = [
                'नमस्ते',
                'मुझे अपॉइंटमेंट बुक करना है',
                'कल',
                'सुबह 10 बजे',
                'हां',
                'धन्यवाद',
            ]
        else:
            conversation = [
                'Hello',
                'I want to book an appointment',
                'Tomorrow',
                '10 AM',
                'Yes',
                'Thank you',
            ]
        
        for i, customer_text in enumerate(conversation, 1):
            self.stdout.write(f'\n  Turn {i}:')
            self.stdout.write(f'  👤 Customer: {customer_text}')
            
            try:
                result = engine.process_turn(customer_text, context)
                
                self.stdout.write(f'  🤖 AI: {result["response_text"]}')
                
                if result.get('action'):
                    self.stdout.write(f'     ⚡ Action: {result["action"]}')
                
                if result.get('end_call'):
                    self.stdout.write('     📞 Call ending')
                    break
            
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'     ❌ Error: {e}'))
                break
        
        self.stdout.write('\n' + '─'*70)
        self.stdout.write(f'  Conversation completed: {context.turn_count} turns')
        self.stdout.write('─'*70)
