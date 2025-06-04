import os
import requests
import time
import logging
from typing import Optional
import threading
from pathlib import Path
import subprocess

# Создаем папку для временных файлов
TMP_DIR = Path("/tmp/pjsua_tts")
TMP_DIR.mkdir(exist_ok=True)

class ElevenLabsTTS:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ELEVENLABS_API_KEY')
        self.voice_id = "wqS2JTzjt7fARO3ZxCVZ"
        self.model_id = "eleven_flash_v2_5"
        self.base_url = "https://api.elevenlabs.io"
        
        if not self.api_key:
            raise ValueError("ElevenLabs API key не найден в переменных окружения")
            
        logging.info(f"[TTS] ElevenLabs TTS инициализирован с voice_id: {self.voice_id}")

    def text_to_speech(self, text: str, output_format: str = "mp3_44100_128") -> Optional[str]:
        """
        Преобразует текст в аудио через ElevenLabs API
        
        Args:
            text: Текст для озвучки
            output_format: Формат выходного аудио
            
        Returns:
            Путь к созданному WAV-файлу или None при ошибке
        """
        if not text.strip():
            logging.warning("[TTS] Пустой текст для озвучки")
            return None
            
        url = f"{self.base_url}/v1/text-to-speech/{self.voice_id}"
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Используем параметры для максимальной скорости
        params = {
            "output_format": output_format,
            "optimize_streaming_latency": 3
        }
        
        data = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.4,
                "speed": 1.07,
            }
        }
        
        try:
            start_time = time.time()
            response = requests.post(url, headers=headers, params=params, json=data, timeout=10)
            
            if response.status_code == 200:
                # Генерируем уникальное имя файла
                timestamp = int(time.time() * 1000)
                mp3_filename = f"tts_{timestamp}.mp3"
                wav_filename = f"tts_{timestamp}.wav"
                mp3_filepath = TMP_DIR / mp3_filename
                wav_filepath = TMP_DIR / wav_filename
                
                # Сохраняем MP3
                with open(mp3_filepath, 'wb') as f:
                    f.write(response.content)
                
                # Конвертируем MP3 в WAV с параметрами PJSUA (16kHz mono)
                try:
                    subprocess.run([
                        'ffmpeg', '-i', str(mp3_filepath), 
                        '-ar', '16000', '-ac', '1', '-y',
                        str(wav_filepath)
                    ], check=True, capture_output=True)
                    
                    # Удаляем временный MP3
                    mp3_filepath.unlink()
                    
                    duration = time.time() - start_time
                    logging.info(f"[TTS] Аудио создано: {wav_filename} (время: {duration:.2f}с)")
                    return str(wav_filepath)
                    
                except subprocess.CalledProcessError as e:
                    logging.error(f"[TTS] Ошибка конвертации MP3->WAV: {e}")
                    # Если ffmpeg недоступен, возвращаем MP3
                    logging.warning("[TTS] Возвращаем MP3 файл (ffmpeg недоступен)")
                    return str(mp3_filepath)
                except FileNotFoundError:
                    logging.warning("[TTS] ffmpeg не найден, возвращаем MP3 файл")
                    return str(mp3_filepath)
            else:
                logging.error(f"[TTS] Ошибка API ElevenLabs: {response.status_code} - {response.text}")
                return None
                
        except requests.RequestException as e:
            logging.error(f"[TTS] Ошибка сети при обращении к ElevenLabs: {e}")
            return None
        except Exception as e:
            logging.error(f"[TTS] Неожиданная ошибка TTS: {e}")
            return None

    def text_to_speech_async(self, text: str, callback=None) -> None:
        """
        Асинхронное преобразование текста в аудио
        
        Args:
            text: Текст для озвучки
            callback: Функция обратного вызова с результатом (filepath или None)
        """
        def worker():
            filepath = self.text_to_speech(text)
            if callback:
                callback(filepath)
                
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

# Глобальный экземпляр TTS
_tts_instance = None

def get_tts_instance() -> ElevenLabsTTS:
    """Получает глобальный экземпляр TTS"""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = ElevenLabsTTS()
    return _tts_instance

def text_to_speech(text: str) -> Optional[str]:
    """Удобная функция для синхронного TTS"""
    tts = get_tts_instance()
    return tts.text_to_speech(text)

def text_to_speech_async(text: str, callback=None) -> None:
    """Удобная функция для асинхронного TTS"""
    tts = get_tts_instance()
    tts.text_to_speech_async(text, callback)
