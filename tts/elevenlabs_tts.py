import os
import requests
import wave
import logging
import io
import subprocess
import tempfile

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16 бит = 2 байта

from dotenv import load_dotenv
load_dotenv()

ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
if not ELEVENLABS_API_KEY:
    logging.error('Не задан ElevenLabs API key в переменной ELEVENLABS_API_KEY')
    exit(1)

VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', 'EXAVITQu4vr4xnSDxMaL')  # Можно переопределить через .env
OUTPUT_DIR = os.getenv('ELEVENLABS_OUTPUT_DIR', 'tts/generated')

# Создаем директорию для файлов, если она не существует
os.makedirs(OUTPUT_DIR, exist_ok=True)

class ElevenLabsTTSSession:
    def __init__(self, voice_id=VOICE_ID):
        self.voice_id = voice_id
        self.api_key = ELEVENLABS_API_KEY
        self.url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def synthesize(self, text, wav_file, output_dir=None):
        # Используем /dev/shm для временных файлов (RAM-диск)
        shm_dir = '/dev/shm' if os.path.isdir('/dev/shm') else None
        temp_dir = shm_dir or tempfile.gettempdir()
        # Имя итогового файла (WAV) в RAM
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            out_wav_path = os.path.join(output_dir, os.path.basename(wav_file))
        else:
            out_wav_path = os.path.join(temp_dir, os.path.basename(wav_file))
        # Временный файл для скачивания ElevenLabs (mp3/ogg)
        with tempfile.NamedTemporaryFile(dir=temp_dir, suffix='.temp', delete=False) as temp_audio:
            temp_file = temp_audio.name
        payload = {
            "text": text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "speed": 1.1,
                "stability": 0.35,
                "similarity_boost": 0.65,
            }
        }
        response = requests.post(self.url, headers=self.headers, json=payload, stream=True)
        if response.status_code != 200:
            raise Exception(f"Ошибка ElevenLabs API: {response.status_code} {response.text}")
        # Сохраняем аудио во временный файл в RAM
        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    f.write(chunk)
        # Конвертируем в нужный формат WAV через ffmpeg (тоже в RAM)
        cmd = [
            'ffmpeg',
            '-y',
            '-i', temp_file,
            '-acodec', 'pcm_s16le',
            '-ar', str(RATE),
            '-ac', str(CHANNELS),
            out_wav_path
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.unlink(temp_file)
            return out_wav_path
        except subprocess.CalledProcessError as e:
            raise Exception(f"Ошибка при конвертации аудио: {e}")
        except Exception as e:
            raise Exception(f"Ошибка при обработке аудио: {e}")

def tts_to_wav(text, wav_file, voice_id=VOICE_ID, output_dir=OUTPUT_DIR):
    # output_dir=None — по умолчанию используем RAM (/dev/shm)
    session = ElevenLabsTTSSession(voice_id)
    return session.synthesize(text, wav_file, output_dir=output_dir) 