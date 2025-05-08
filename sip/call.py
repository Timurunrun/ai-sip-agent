import threading
import os
import time
import pjsua2 as pj
from stt.deepgram_stt import stt_from_wav, DeepgramSTTSession  # импортируем функцию STT и новый класс STT
from sip.utils import get_active_lead_id  # импортируем функцию get_active_lead_id

class Call(pj.Call):
    current = None  # Ссылка на текущий активный звонок
    def __init__(self, acc, call_id=pj.PJSUA_INVALID_ID):
        super().__init__(acc, call_id)
        self.acc = acc
        self.connected = False
        self.audio_streaming = False
        self.stop_streaming = threading.Event()
        self._recorder = None
        self._stream_thread = None
        self._audio_media = None
        self._stt_session = None  # объект сессии STT
        self._recording_filename = None  # имя файла для записи
        Call.current = self  # Установить текущий звонок

    def onCallState(self, prm):
        ci = self.getInfo()
        print(f"[PJSUA] Состояние вызова: {ci.stateText}, Код: {ci.lastStatusCode}")
        
        if ci.stateText == "DISCONNECTED":
            self.connected = False
            
            # 1. Сначала останавливаем стриминг аудио
            self.stop_streaming.set()
            
            # 2. Проверяем состояние медиа перед остановкой
            try:
                if self._audio_media and self._recorder:
                    # Проверяем, активно ли медиа
                    for mi in ci.media:
                        if (mi.type == pj.PJMEDIA_TYPE_AUDIO and 
                            mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE):
                            self._audio_media.stopTransmit(self._recorder)
                            break
            except Exception as e:
                print(f"[PJSUA] Ошибка при остановке аудио: {e}")
            
            # 3. Ждем завершения потока стриминга
            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=1.0)
            
            # 4. Освобождаем ресурсы медиа
            try:
                if self._recorder:
                    self._recorder = None
                if self._audio_media:
                    self._audio_media = None
            except Exception as e:
                print(f"[PJSUA] Ошибка при освобождении медиа ресурсов: {e}")
            
            # 5. Очищаем остальные ресурсы
            if hasattr(self.acc.sip_event_queue, 'current_call'):
                self.acc.sip_event_queue.current_call = None
            Call.current = None
            print("[PJSUA] Вызов завершен и ресурсы освобождены")

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                print("[PJSUA] Медиа активно, запускаем запись аудиофайла...")
                try:
                    si = self.getStreamInfo(mi.index)
                    print(f"[PJSUA] Кодек: {si.codecName} @ {si.codecClockRate} Hz")
                except Exception as e:
                    print(f"[PJSUA] Не удалось получить информацию о кодеке: {e}")
                self.start_audio_streaming(mi.index)

    def connect_stt_session(self, filename):
        self._recording_filename = filename
        self._stt_session = DeepgramSTTSession(filename)
        self._stt_session.connect()

    def start_audio_streaming(self, media_index):
        if self.audio_streaming:
            return
        self.audio_streaming = True
        filename = self._recording_filename
        print(f"[PJSUA] Запись идёт: {filename}")
        try:
            self._recorder = pj.AudioMediaRecorder()
            self._recorder.createRecorder(filename)
            self._audio_media = pj.AudioMedia.typecastFromMedia(self.getMedia(media_index))
            self._audio_media.startTransmit(self._recorder)
            # --- Запуск отправки аудио в Deepgram ---
            if self._stt_session:
                self._stt_session.start_streaming()
        except Exception as e:
            print(f"[PJSUA] Ошибка при инициализации аудио: {e}")
            return