"""
sarvam/intent_detector.py – Phase 8.1: Intent Detection
==========================================================

Rule-based intent detection for Indian languages.
Detects customer intent from transcribed speech.

Supported Intents:
- book_appointment
- cancel_appointment
- product_inquiry
- pricing_inquiry
- complaint
- transfer_human
- confirm_yes
- confirm_no
- greeting
- goodbye
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class IntentDetector:
    """
    Detects customer intent from text in multiple Indian languages.
    Uses rule-based pattern matching (expandable to ML models later).
    """
    
    def __init__(self, language: str = 'hi-IN'):
        self.language = language
        self.intent_patterns = self._load_patterns()
    
    def detect(self, text: str) -> Dict:
        """
        Detect intent from customer text.
        
        Args:
            text: Customer's spoken text (transcribed)
        
        Returns:
            {
                'intent': 'book_appointment',
                'confidence': 0.95,
                'entities': {'date': '15 मार्च', 'time': '10 बजे'},
                'matched_pattern': 'appointment booking pattern'
            }
        """
        if not text or not text.strip():
            return {
                'intent': 'unknown',
                'confidence': 0.0,
                'entities': {},
            }
        
        text_lower = text.lower().strip()
        
        # Check each intent pattern
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if self._matches_pattern(text_lower, pattern):
                    entities = self._extract_entities(text, intent)
                    return {
                        'intent': intent,
                        'confidence': 0.92,
                        'entities': entities,
                        'matched_pattern': pattern,
                    }
        
        # No match found
        return {
            'intent': 'unknown',
            'confidence': 0.0,
            'entities': {},
        }
    
    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """Check if text matches pattern (keywords or regex)."""
        # Simple keyword matching
        keywords = pattern.split('|')
        return any(kw.strip() in text for kw in keywords)
    
    def _extract_entities(self, text: str, intent: str) -> Dict:
        """
        Extract entities from text based on intent.
        
        Examples:
        - Date: "15 मार्च", "tomorrow", "next week"
        - Time: "10 बजे", "morning", "evening"
        - Product: product names, services
        """
        entities = {}
        
        # Date extraction
        date_patterns = {
            'hi-IN': r'(\d+\s*(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर))',
            'en-IN': r'(\d+\s*(?:january|february|march|april|may|june|july|august|september|october|november|december))',
        }
        
        if intent in ['book_appointment', 'cancel_appointment']:
            # Extract date
            date_pattern = date_patterns.get(self.language, date_patterns['en-IN'])
            date_match = re.search(date_pattern, text.lower())
            if date_match:
                entities['date'] = date_match.group(1)
            
            # Common date keywords
            date_keywords = {
                'hi-IN': {
                    'आज': 'today',
                    'कल': 'tomorrow',
                    'परसों': 'day_after_tomorrow',
                    'अगले हफ्ते': 'next_week',
                },
                'en-IN': {
                    'today': 'today',
                    'tomorrow': 'tomorrow',
                    'next week': 'next_week',
                }
            }
            
            for keyword, value in date_keywords.get(self.language, {}).items():
                if keyword in text.lower():
                    entities['date_relative'] = value
                    break
            
            # Extract time
            time_patterns = {
                'hi-IN': r'(\d+\s*बजे)',
                'en-IN': r'(\d+\s*(?:am|pm|o\'?clock))',
            }
            time_pattern = time_patterns.get(self.language, time_patterns['en-IN'])
            time_match = re.search(time_pattern, text.lower())
            if time_match:
                entities['time'] = time_match.group(1)
            
            # Time of day
            if any(word in text.lower() for word in ['सुबह', 'morning']):
                entities['time_of_day'] = 'morning'
            elif any(word in text.lower() for word in ['दोपहर', 'afternoon', 'noon']):
                entities['time_of_day'] = 'afternoon'
            elif any(word in text.lower() for word in ['शाम', 'evening']):
                entities['time_of_day'] = 'evening'
        
        return entities
    
    def _load_patterns(self) -> Dict[str, List[str]]:
        """Load intent patterns for the configured language."""
        
        patterns = {
            'hi-IN': {
                'book_appointment': [
                    'अपॉइंटमेंट|बुक|appointment|schedule|मिलना',
                    'समय|टाइम|मीटिंग',
                ],
                'cancel_appointment': [
                    'कैंसल|रद्द|cancel|remove|हटा',
                ],
                'product_inquiry': [
                    'प्रोडक्ट|सामान|product|service|सर्विस',
                    'क्या|जानकारी|बताओ|information',
                ],
                'pricing_inquiry': [
                    'कीमत|price|cost|खर्च|दाम|रेट|rate',
                    'कितना|kitna|how much',
                ],
                'complaint': [
                    'शिकायत|complaint|समस्या|problem|issue|परेशानी',
                    'काम नहीं|not working|खराब',
                ],
                'transfer_human': [
                    'इंसान|मैनेजर|manager|human|person|व्यक्ति',
                    'किसी से बात|talk to someone',
                ],
                'confirm_yes': [
                    'हां|जी|yes|okay|ठीक|सही|bilkul|sure',
                ],
                'confirm_no': [
                    'नहीं|no|nahi|mat|don\'t',
                ],
                'greeting': [
                    'नमस्ते|हेलो|hello|hi|hey|namaste',
                ],
                'goodbye': [
                    'धन्यवाद|thank|thanks|शुक्रिया|bye|goodbye|अलविदा',
                ],
            },
            'en-IN': {
                'book_appointment': [
                    'appointment|book|schedule|meeting|meet',
                ],
                'cancel_appointment': [
                    'cancel|remove|delete appointment',
                ],
                'product_inquiry': [
                    'product|service|information|tell me about',
                    'what|which|how',
                ],
                'pricing_inquiry': [
                    'price|cost|rate|charge|fee',
                    'how much|what is the price',
                ],
                'complaint': [
                    'complaint|problem|issue|not working',
                    'broken|defective|wrong',
                ],
                'transfer_human': [
                    'human|person|manager|supervisor|agent',
                    'talk to someone|speak with',
                ],
                'confirm_yes': [
                    'yes|yeah|sure|okay|correct|right',
                ],
                'confirm_no': [
                    'no|nope|not|don\'t',
                ],
                'greeting': [
                    'hello|hi|hey|good morning|good evening',
                ],
                'goodbye': [
                    'thank you|thanks|bye|goodbye',
                ],
            },
            'ta-IN': {
                'book_appointment': [
                    'சந்திப்பு|appointment|நேரம்|time',
                ],
                'cancel_appointment': [
                    'ரத்து|cancel|நீக்கு',
                ],
                'product_inquiry': [
                    'தயாரிப்பு|product|சேவை|service',
                ],
                'pricing_inquiry': [
                    'விலை|price|செலவு|cost',
                ],
                'complaint': [
                    'புகார்|complaint|பிரச்சனை|problem',
                ],
                'transfer_human': [
                    'மனிதர்|human|மேலாளர்|manager',
                ],
                'confirm_yes': [
                    'ஆம்|yes|சரி|okay',
                ],
                'confirm_no': [
                    'இல்லை|no|வேண்டாம்',
                ],
                'greeting': [
                    'வணக்கம்|hello|hi',
                ],
                'goodbye': [
                    'நன்றி|thanks|bye',
                ],
            },
        }
        
        return patterns.get(self.language, patterns['en-IN'])


# Singleton
_intent_detector = None

def get_intent_detector(language: str = 'hi-IN') -> IntentDetector:
    """Get or create intent detector for language."""
    global _intent_detector
    if _intent_detector is None or _intent_detector.language != language:
        _intent_detector = IntentDetector(language)
    return _intent_detector
