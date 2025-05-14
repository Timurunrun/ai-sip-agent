import os
import requests
import wave
import logging
import io
import subprocess

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
        # Если output_dir задан, обновляем путь к wav_file
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            if os.path.isabs(wav_file):
                wav_file = os.path.join(output_dir, os.path.basename(wav_file))
            else:
                wav_file = os.path.join(output_dir, wav_file)
        
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
        
        # Создаем директорию для файла, если ее нет
        os.makedirs(os.path.dirname(os.path.abspath(wav_file)), exist_ok=True)
        
        # Сохраняем полученное аудио во временный файл
        temp_file = wav_file + ".temp"
        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    f.write(chunk)
        
        # Конвертируем в нужный формат WAV через ffmpeg
        cmd = [
            'ffmpeg',
            '-y',
            '-i', temp_file,
            '-acodec', 'pcm_s16le',
            '-ar', str(RATE),
            '-ac', str(CHANNELS),
            wav_file
        ]
        
        try:
            subprocess.run(cmd, check=True)
            # Удаляем временный файл
            os.unlink(temp_file)
            return wav_file
        except subprocess.CalledProcessError as e:
            raise Exception(f"Ошибка при конвертации аудио: {e}")
        except Exception as e:
            raise Exception(f"Ошибка при обработке аудио: {e}")

def tts_to_wav(text, wav_file, voice_id=VOICE_ID, output_dir=OUTPUT_DIR):
    session = ElevenLabsTTSSession(voice_id)
    return session.synthesize(text, wav_file, output_dir=output_dir) 