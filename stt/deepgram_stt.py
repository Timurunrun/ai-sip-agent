import os
import threading
import asyncio
import websockets
import wave
import json
import logging
from llm.groq_agent import process_transcript, process_transcript_async
import random
import queue
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

RATE = 16000
CHANNELS = 1
CHUNK = 4096

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
        self._last_utterance_end_time = None

    async def _connect_ws(self):
        url = (
            f"wss://api.deepgram.com/v1/listen"
            f"?encoding=linear16"
            f"&sample_rate={RATE}"
            f"&channels={CHANNELS}"
            f"&interim_results=true"
            # f"&punctuate=true"
            f"&utterance_end_ms=1000"
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
            no_data_count = 0
            while not self.stop_event.is_set():
                f_read.seek(position)
                chunk = f_read.read(CHUNK * 2)
                if chunk:
                    await self.ws.send(chunk)
                    position += len(chunk)
                    no_data_count = 0
                else:
                    no_data_count += 1
                    # Динамическая задержка для увеличения скорости (начинаем с малой, увеличиваем при отсутствии данных)
                    delay = min(0.02 + (no_data_count * 0.01), 0.1)
                    await asyncio.sleep(delay)
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
                self._last_utterance_end_time = time.time()
                print(f"[UTTERANCE END] Конец речи в {last_word_end}s (ts={self._last_utterance_end_time:.3f})")
                full_text = ' '.join([b.strip() for b in buffer]).strip()
                if full_text:
                    print(f"[STT] Расшифровка: {full_text}")
                    def llm_thread():
                        import inspect
                        import time as _time
                        try:
                            if inspect.iscoroutinefunction(process_transcript_async):
                                try:
                                    loop = asyncio.get_running_loop()
                                except RuntimeError:
                                    loop = None
                                if loop and loop.is_running():
                                    fut = asyncio.run_coroutine_threadsafe(process_transcript_async(full_text), loop)
                                    llm_response = fut.result()
                                else:
                                    llm_response = asyncio.run(process_transcript_async(full_text))
                            else:
                                llm_response = process_transcript(full_text)
                        except Exception as e:
                            llm_response = f"[LLM] Ошибка: {e}"
                        delay_ms = None
                        if self._last_utterance_end_time:
                            delay_ms = int((_time.time() - self._last_utterance_end_time) * 1000)
                        if delay_ms is not None:
                            print(f"[LLM] Ответ: {llm_response} (задержка {delay_ms} мс)")
                        else:
                            print(f"[LLM] Ответ: {llm_response}")
                    threading.Thread(target=llm_thread, daemon=True).start()
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
        self.connected_event.wait()
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

    def close(self):
        if self.ws is None or self.loop is None:
            return
        async def _close_ws():
            try:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await asyncio.sleep(0.2)
                await self.ws.close()
            except Exception as e:
                logging.error(f"Ошибка при закрытии Deepgram WebSocket: {e}")
        try:
            if self.loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_close_ws(), self.loop)
            else:
                self.loop.run_until_complete(_close_ws())
        except Exception as e:
            logging.error(f"Ошибка при завершении Deepgram STT: {e}")

def stt_from_wav(wav_file):
    session = DeepgramSTTSession(wav_file)
    session.connect()
    session.start_streaming()
    return session 