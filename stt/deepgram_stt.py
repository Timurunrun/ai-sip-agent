import os
import threading
import asyncio
import websockets
import wave
import json
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

RATE = 16000
CHANNELS = 1
CHUNK = 1024

from dotenv import load_dotenv
load_dotenv()

DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
if not DEEPGRAM_API_KEY:
    logging.error('Не задан Deepgram API key в переменной DEEPGRAM_API_KEY')
    exit(1)

stop_event = threading.Event()

def stt_from_wav(wav_file, on_utterance_end=None):
    async def send_and_receive():
        url = (
            f"wss://api.deepgram.com/v1/listen"
            f"?encoding=linear16"
            f"&sample_rate={RATE}"
            f"&channels={CHANNELS}"
            f"&interim_results=true"
            f"&punctuate=true"
            f"&utterance_end_ms=2000"
            f"&endpointing=300"
            f"&vad_events=true"
            f"&language=ru"
            f"&model=nova-2"
        )
        headers = {
            'Authorization': f'Token {DEEPGRAM_API_KEY}'
        }

        async with websockets.connect(url, additional_headers=headers) as ws:
            logging.info('Подключено к Deepgram Realtime API')

            buffer = []  # Буфер для накопления строк

            async def send_loop():
                with open(wav_file, 'rb') as f_read:
                    f_read.seek(44)
                    position = 44
                    while not stop_event.is_set():
                        f_read.seek(position)
                        chunk = f_read.read(CHUNK * 2)
                        if chunk:
                            await ws.send(chunk)
                            position += len(chunk)
                        else:
                            await asyncio.sleep(0.1)
                    await ws.send(json.dumps({"type": "CloseStream"}))

            async def receive_loop():
                nonlocal buffer
                async for message in ws:
                    data = json.loads(message)
                    if 'type' in data and data['type'] == 'SpeechStarted':
                        timestamp = data.get('timestamp', 0)
                        print(f"[VAD EVENT] SpeechStarted at {timestamp}s")
                        continue
                    if 'type' in data and data['type'] == 'UtteranceEnd':
                        last_word_end = data.get('last_word_end', 0)
                        print(f"[UTTERANCE END] Конец речи в {last_word_end}s")
                        # --- Отправляем накопленный текст в callback ---
                        full_text = ''.join(buffer).strip()
                        if full_text and on_utterance_end:
                            on_utterance_end(full_text)
                        buffer = []
                        continue
                    if 'channel' in data:
                        if isinstance(data['channel'], dict):
                            is_final = data.get('is_final', False)
                            if is_final:
                                channel = data['channel']
                                alts = channel.get('alternatives', [])
                                if alts and len(alts) > 0:
                                    transcript = alts[0].get('transcript', '').strip()
                                    if transcript:
                                        print(transcript)
                                        buffer.append(transcript + '\n')

            await asyncio.gather(send_loop(), receive_loop())

    def run():
        try:
            asyncio.run(send_and_receive())
        except KeyboardInterrupt:
            logging.info('Получен KeyboardInterrupt, останавливаем...')
        finally:
            stop_event.set()
            logging.info('STT-модуль завершён.')

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread 