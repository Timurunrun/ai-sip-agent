import os
import threading
import asyncio
import websockets
import json
import logging
from llm.live_call import process_transcript, process_transcript_async
import time
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from dotenv import load_dotenv
load_dotenv()

def load_speech_config():
    config_path = os.path.join(os.path.dirname(__file__), 'speech_config.json')
    if not os.path.exists(config_path):
        logging.error(f"Файл конфигурации {config_path} не найден")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка чтения конфигурации: {e}")
        return None

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
        cfg = load_speech_config() or {}
        self.config = cfg.get('Deepgram', {})
        self._interjections_enabled = bool(self.config.get('interjections_enabled', False))

    async def _connect_ws(self):
        url = (
            f"wss://api.deepgram.com/v1/listen"
            f"?encoding={self.config.get('encoding', 'linear16')}"
            f"&sample_rate={self.config.get('sample_rate', 16000)}"
            f"&channels={self.config.get('channels', 1)}"
            f"&interim_results={self.config.get('interim_results', 'true')}"
            f"&endpointing={self.config.get('endpointing', '100')}"
            f"&utterance_end_ms={self.config.get('utterance_end_ms', '1000')}"
            f"&vad_events={self.config.get('vad_events', 'true')}"
            f"&language={self.config.get('language', 'ru')}"
            f"&model={self.config.get('model', '')}"
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
                chunk = f_read.read(self.config.get('chunk', 1600) * 2)
                if chunk:
                    try:
                        if self.ws is None or getattr(self.ws, 'closed', False):    # Если соединение уже закрыто, выходим
                            break
                        await self.ws.send(chunk)
                    # Соединение закрыто, прекращаем отправку
                    except websockets.exceptions.ConnectionClosedOK:
                        break
                    except websockets.exceptions.ConnectionClosed:
                        break
                    position += len(chunk)
                    no_data_count = 0
                else:
                    no_data_count += 1
                    # Динамическая задержка для увеличения скорости (начинаем с малой, увеличиваем при отсутствии данных)
                    delay = min(0.02 + (no_data_count * 0.01), 0.1)
                    await asyncio.sleep(delay)
            # Сигнал о завершении потока, если соединение ещё открыто
            try:
                if self.ws and not getattr(self.ws, 'closed', False):
                    await self.ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass

    async def _receive_loop(self):
        buffer = []
        try:
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
                    full_text = ' '.join([str(b).strip() for b in buffer]).strip()
                    if full_text:
                        print(f"[STT] Расшифровка: {full_text}")

                        if self._interjections_enabled:
                            def play_interjection():
                                try:
                                    inter_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'audio', 'interjections'))
                                    if not os.path.isdir(inter_dir):
                                        logging.debug(f"[INTERJECTION] Директория не найдена: {inter_dir}")
                                        return
                                    files = [f for f in os.listdir(inter_dir) if f.lower().endswith('.wav')]
                                    if not files:
                                        logging.debug("[INTERJECTION] Нет .wav файлов в interjections")
                                        return
                                    chosen = random.choice(files)
                                    full_path = os.path.join(inter_dir, chosen)
                                    from sip.audio_player import queue_audio_for_playback
                                    queue_audio_for_playback(full_path)
                                    logging.info(f"[INTERJECTION] Проигрывается: {chosen}")
                                except Exception as e:
                                    logging.debug(f"[INTERJECTION] Ошибка: {e}")
                            threading.Thread(target=play_interjection, daemon=True).start()

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
                                logging.info(f"[LLM] Ответ готов (задержка {delay_ms} мс)")
                            else:
                                logging.info(f"[LLM] Ответ готов")
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
        except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosed):
            pass

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
            done = self.loop.run_until_complete(asyncio.gather(
                self._send_task,
                self._recv_task,
                return_exceptions=True
            ))
            for exc in done:
                if isinstance(exc, Exception):
                    if isinstance(exc, (asyncio.CancelledError, websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosed)):
                        continue
                    logging.debug(f"[Deepgram] Task finished with exception: {exc}")
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def close(self):
        self.stop_event.set()
        if self.loop is None:
            return

        async def _shutdown():
            # Пытаемся корректно завершить отправку/приём
            try:
                if self.ws and not getattr(self.ws, 'closed', False):
                    try:
                        await self.ws.send(json.dumps({"type": "CloseStream"}))
                        await asyncio.sleep(0.1)
                    except Exception:
                        pass
            finally:
                # Отменяем задачи, если они ещё активны
                for task in (self._send_task, self._recv_task):
                    try:
                        if task and not task.done():
                            task.cancel()
                    except Exception:
                        pass
                # Закрываем сокет
                try:
                    if self.ws and not getattr(self.ws, 'closed', False):
                        await self.ws.close()
                except Exception:
                    pass

        try:
            if self.loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
                # Ждём немного, чтобы корректно завершиться
                try:
                    fut.result(timeout=1.0)
                except Exception:
                    pass
            else:
                self.loop.run_until_complete(_shutdown())
        except Exception as e:
            logging.debug(f"Ошибка при завершении Deepgram STT: {e}")
