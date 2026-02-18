"""
sarvam/tts_service.py  –  Phase 7: Sarvam AI TTS Integration
==============================================================

Sarvam AI Text-to-Speech:  https://docs.sarvam.ai/api-reference/tts

Generates .wav / .mp3 audio files for:
    • IVR prompts
    • Voicemail drop messages
    • AMD (answering machine) messages
    • Campaign greeting messages

Supported languages (Sarvam AI):
    hi-IN  Hindi
    en-IN  Indian English
    ta-IN  Tamil
    te-IN  Telugu
    kn-IN  Kannada
    ml-IN  Malayalam
    mr-IN  Marathi
    gu-IN  Gujarati
    bn-IN  Bengali
    or-IN  Odia
    pa-IN  Punjabi

Usage:
    from sarvam.tts_service import SarvamTTS

    tts = SarvamTTS()
    path = tts.generate(
        text='Namaste, aapka call receive hua hai.',
        language='hi-IN',
        voice='meera',
        output_name='campaign_1_greeting'
    )
    # path → /var/spool/asterisk/sounds/tts/campaign_1_greeting.wav
"""

import os
import logging
import hashlib
import requests
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
SARVAM_API_KEY  = getattr(settings, 'SARVAM_API_KEY', '')
SARVAM_TTS_URL  = 'https://api.sarvam.ai/text-to-speech'
TTS_AUDIO_DIR   = getattr(
    settings, 'TTS_AUDIO_DIR',
    '/var/spool/asterisk/sounds/tts'
)

# Sarvam voice options per language
# Sarvam voice options (updated from API validation error)
# Note: Sarvam supports multiple languages per voice, simplified mapping here.
VALID_VOICES = [
    'aditi', 'anushka', 'arti', 'bhavna', 'diya', 'kavya', 'manisha', 'neha', 'pooja', 'priya', 'ritu', 'roopa', 'shreya', 'simran', 'vidya',  # Female
    'abhilash', 'aditya', 'amit', 'amartya', 'arvind', 'arya', 'dev', 'dhruv', 'hitesh', 'ishita', 'karun', 'manan', 'rahul', 'ratan', 'rohan', 'sumit', 'varun' # Male
]

VOICE_OPTIONS = {
    'hi-IN': ['meera', 'pavithra', 'maitreyi', 'arvind', 'amol', 'amartya'], # Keep old for ref if needed, but overwriting below
}

# Updated mapping based on known Sarvam voices (generic assignment for now)
# Updated mapping based on API validation error for bulbul:v3
ALL_VOICES = [
    'aditya', 'ritu', 'ashutosh', 'priya', 'neha', 'rahul', 'pooja', 
    'rohan', 'simran', 'kavya', 'amit', 'dev', 'ishita', 'shreya', 
    'ratan', 'varun', 'manan', 'sumit', 'roopa', 'kabir', 'aayan', 
    'shubh', 'advait', 'amelia', 'sophia', 'ana'
]

# Map all languages to the full list of supported voices
VOICE_OPTIONS = {
    'hi-IN': ALL_VOICES,
    'en-IN': ALL_VOICES,
    'ta-IN': ALL_VOICES,
    'te-IN': ALL_VOICES,
    'kn-IN': ALL_VOICES,
    'ml-IN': ALL_VOICES,
    'mr-IN': ALL_VOICES,
    'gu-IN': ALL_VOICES,
    'bn-IN': ALL_VOICES,
    'pa-IN': ALL_VOICES,
}

LANGUAGE_CHOICES = [
    ('hi-IN', 'Hindi (हिन्दी)'),
    ('en-IN', 'Indian English'),
    ('ta-IN', 'Tamil (தமிழ்)'),
    ('te-IN', 'Telugu (తెలుగు)'),
    ('kn-IN', 'Kannada (ಕನ್ನಡ)'),
    ('ml-IN', 'Malayalam (മലയാളം)'),
    ('mr-IN', 'Marathi (मराठी)'),
    ('gu-IN', 'Gujarati (ગુજરાતી)'),
    ('bn-IN', 'Bengali (বাংলা)'),
    ('pa-IN', 'Punjabi (ਪੰਜਾਬੀ)'),
]


# ─── Service class ────────────────────────────────────────────────────────────
class SarvamTTS:
    """
    Wrapper around Sarvam AI TTS API.
    Results are cached to disk — same text+lang+voice won't re-generate.
    """

    def __init__(self, api_key: str = ''):
        self.api_key = api_key or SARVAM_API_KEY
        self.audio_dir = Path(TTS_AUDIO_DIR)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    # ── Public: generate (cached) ─────────────────────────────────────────
    def generate(
        self,
        text: str,
        language: str = 'hi-IN',
        voice: str = 'aditya',
        output_name: str = '',
        force: bool = False,
    ) -> Optional[str]:
        """
        Generate TTS audio and return the local file path.

        Args:
            text:        The text to speak (max ~500 chars per Sarvam limit)
            language:    BCP-47 language code, e.g. 'hi-IN'
            voice:       Sarvam voice name
            output_name: Prefix for the saved file (auto-generated if blank)
            force:       Regenerate even if cached file exists

        Returns:
            Absolute path to the .wav file, or None on error.
        """
        if not text.strip():
            logger.warning('SarvamTTS.generate: empty text, skipping')
            return None

        if not self.api_key:
            logger.error('SARVAM_API_KEY is not configured in settings.py')
            return None

        # Cache key — same text+lang+voice → same file
        cache_key = hashlib.md5(f'{text}|{language}|{voice}'.encode()).hexdigest()[:12]
        filename  = f'{output_name or "tts"}_{cache_key}.wav'
        filepath  = self.audio_dir / filename

        if filepath.exists() and not force:
            logger.debug(f'SarvamTTS: cache hit → {filepath}')
            return str(filepath)

        # ── Call Sarvam API ───────────────────────────────────────────────
        try:
            payload = {
                'inputs':        [text],
                'target_language_code': language,
                'speaker':       voice,
                'speech_sample_rate': 8000,   # 8 kHz for Asterisk compatibility
                'enable_preprocessing': True,
                'model': 'bulbul:v3',
            }

            headers = {
                'api-subscription-key': self.api_key,
                'Content-Type': 'application/json',
            }

            resp = requests.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            audios = data.get('audios', [])
            if not audios:
                logger.error(f'Sarvam TTS: no audio in response: {data}')
                return None

            # Response is base64-encoded WAV
            import base64
            audio_bytes = base64.b64decode(audios[0])

            filepath.write_bytes(audio_bytes)
            logger.info(f'SarvamTTS: generated → {filepath}  ({len(audio_bytes):,} bytes)')
            return str(filepath)

        except requests.HTTPError as e:
            logger.error(f'Sarvam TTS HTTP error: {e.response.status_code} – {e.response.text[:300]}')
            return None
        except Exception as e:
            logger.error(f'Sarvam TTS error: {e}', exc_info=True)
            return None

    # ── Chunk long text ──────────────────────────────────────────────────
    def generate_long(
        self,
        text: str,
        language: str = 'hi-IN',
        voice: str = 'meera',
        output_name: str = 'long',
    ) -> Optional[str]:
        """
        Split text >500 chars into chunks, generate each, concatenate with
        pydub, and return path to the final WAV.
        Requires: pip install pydub
        """
        MAX_CHARS = 500
        if len(text) <= MAX_CHARS:
            return self.generate(text, language, voice, output_name)

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error('pydub not installed: pip install pydub')
            return None

        # Split on sentence boundaries
        import re
        sentences = re.split(r'(?<=[।.!?])\s+', text)
        chunks, current = [], ''
        for s in sentences:
            if len(current) + len(s) + 1 <= MAX_CHARS:
                current = (current + ' ' + s).strip()
            else:
                if current:
                    chunks.append(current)
                current = s
        if current:
            chunks.append(current)

        segment = AudioSegment.empty()
        for i, chunk in enumerate(chunks):
            path = self.generate(chunk, language, voice, f'{output_name}_part{i}')
            if path:
                segment += AudioSegment.from_wav(path)

        out_path = self.audio_dir / f'{output_name}_full.wav'
        segment.export(str(out_path), format='wav')
        logger.info(f'SarvamTTS.generate_long: merged {len(chunks)} chunks → {out_path}')
        return str(out_path)

    # ── Helpers ───────────────────────────────────────────────────────────
    def list_cached_files(self) -> list:
        """Return list of all cached TTS files."""
        return [
            {'name': f.name, 'size': f.stat().st_size, 'path': str(f)}
            for f in sorted(self.audio_dir.glob('*.wav'))
        ]

    def delete_cached(self, filename: str) -> bool:
        """Delete a specific cached file."""
        path = self.audio_dir / filename
        if path.exists():
            path.unlink()
            return True
        return False


# ─── Module-level convenience ─────────────────────────────────────────────────
_tts_instance = None

def get_tts() -> SarvamTTS:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = SarvamTTS()
    return _tts_instance
