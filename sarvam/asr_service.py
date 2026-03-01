"""
sarvam/asr_service.py – Phase 8: Sarvam Speech-to-Text (ASR)
============================================================

Speech recognition using Sarvam Translate API.
Docs: https://docs.sarvam.ai/api-reference-docs/speech-to-text

Supports all Indian languages:
- hi-IN (Hindi)
- en-IN (English)
- ta-IN (Tamil)
- te-IN (Telugu)
- kn-IN (Kannada)
- ml-IN (Malayalam)
- mr-IN (Marathi)
- gu-IN (Gujarati)
- bn-IN (Bengali)
- pa-IN (Punjabi)
- or-IN (Odia)
"""

import logging
import requests
from pathlib import Path
from typing import Optional, Dict
from django.conf import settings

logger = logging.getLogger(__name__)

SARVAM_API_KEY = getattr(settings, 'SARVAM_API_KEY', '')
SARVAM_ASR_URL = 'https://api.sarvam.ai/speech-to-text'


class SarvamASR:
    """
    Sarvam Speech-to-Text service.
    Converts audio files to text in Indian languages.
    """
    
    def __init__(self, api_key: str = ''):
        self.api_key = api_key or SARVAM_API_KEY
    
    def transcribe(
        self,
        audio_file_path: str,
        language_code: str = 'hi-IN',
        model: str = 'saaras:v2',
    ) -> Dict:
        """
        Transcribe audio file to text using Sarvam ASR.
        
        Args:
            audio_file_path: Path to audio file (WAV, MP3, OGG, etc.)
            language_code: Language code (hi-IN, ta-IN, etc.)
            model: Model to use (saaras:v2 is latest)
        
        Returns:
            {
                'text': 'मुझे अपॉइंटमेंट बुक करना है',
                'language_code': 'hi-IN',
                'confidence': 0.95,
                'duration': 3.2,
            }
        """
        if not self.api_key:
            logger.error('SARVAM_API_KEY not configured')
            return {'text': '', 'error': 'API key missing'}
        
        try:
            # Read audio file
            audio_path = Path(audio_file_path)
            if not audio_path.exists():
                logger.error(f'Audio file not found: {audio_file_path}')
                return {'text': '', 'error': 'File not found'}
            
            # Prepare request
            with open(audio_path, 'rb') as audio_file:
                files = {'file': (audio_path.name, audio_file, 'audio/wav')}
                data = {
                    'language_code': language_code,
                    'model': model,
                }
                headers = {
                    'api-subscription-key': self.api_key,
                }
                
                # Call Sarvam API
                response = requests.post(
                    SARVAM_ASR_URL,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                
                result = response.json()
                
                return {
                    'text': result.get('transcript', ''),
                    'language_code': language_code,
                    'confidence': 0.95,  # Sarvam doesn't return confidence yet
                    'duration': 0.0,  # Will be filled by caller if available
                }
        
        except requests.HTTPError as e:
            logger.error(f'Sarvam ASR HTTP error: {e.response.status_code} - {e.response.text[:500]}')
            return {'text': '', 'error': str(e)}
        except Exception as e:
            logger.error(f'Sarvam ASR error: {e}', exc_info=True)
            return {'text': '', 'error': str(e)}


# Singleton
_asr_instance = None

def get_asr() -> SarvamASR:
    """Get or create ASR instance."""
    global _asr_instance
    if _asr_instance is None:
        _asr_instance = SarvamASR()
    return _asr_instance
