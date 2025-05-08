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

class DeepgramSTTSession:
    def __init__(self, wav_file):
        self.wav_file = wav_file
        self.ws = None
        self.stop_event = threading.Event()
        self.loop = None
        self.thread = None
        self.connected_event = threading.Event()
        self._send_task = None
        self._recv_task = None

    async def _connect_ws(self):
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
        self.ws = await websockets.connect(url, additional_headers=headers)
        logging.info('Подключено к Deepgram Realtime API')
        self.connected_event.set()

    async def _send_loop(self):
        with open(self.wav_file, 'rb') as f_read:
            f_read.seek(44)
            position = 44
            while not self.stop_event.is_set():
                f_read.seek(position)
                chunk = f_read.read(CHUNK * 2)
                if chunk:
                    await self.ws.send(chunk)
                    position += len(chunk)
                else:
                    await asyncio.sleep(0.1)
            await self.ws.send(json.dumps({"type": "CloseStream"}))

    async def _receive_loop(self):
        buffer = []
        async for message in self.ws:
            data = json.loads(message)
            if 'type' in data and data['type'] == 'SpeechStarted':
                timestamp = data.get('timestamp', 0)
                print(f"[VAD EVENT] SpeechStarted at {timestamp}s")
                continue
            if 'type' in data and data['type'] == 'UtteranceEnd':
                last_word_end = data.get('last_word_end', 0)
                print(f"[UTTERANCE END] Конец речи в {last_word_end}s")
                full_text = ' '.join([b.strip() for b in buffer]).strip()
                if full_text:
                    print(f"[STT] Расшифровка: {full_text}")
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
                                buffer.append(transcript)

    def connect(self):
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._connect_ws())
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.connected_event.wait()  # Ждём подключения
        return self

    def start_streaming(self):
        def run():
            asyncio.set_event_loop(self.loop)
            self._send_task = self.loop.create_task(self._send_loop())
            self._recv_task = self.loop.create_task(self._receive_loop())
            self.loop.run_until_complete(asyncio.gather(self._send_task, self._recv_task))
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

# Старый интерфейс для обратной совместимости

def stt_from_wav(wav_file):
    session = DeepgramSTTSession(wav_file)
    session.connect()
    session.start_streaming()
    return session 