import threading
import os
import time
import pjsua2 as pj
from stt.deepgram_stt import stt_from_wav, DeepgramSTTSession
from sip.utils import get_active_lead_id

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
        self._stt_session = None
        self._recording_filename = None
        self.lead_id = None
        self._player = None
        self._bg_player = None  # Плеер фонового шума
        Call.current = self

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
                # Освобождаем ресурсы плеера
                if self._player:
                    try:
                        self._player = None
                    except Exception as e:
                        print(f"[PJSUA] Ошибка при освобождении плеера: {e}")
            except Exception as e:
                print(f"[PJSUA] Ошибка при освобождении медиа ресурсов: {e}")
            
            # 5. Очищаем остальные ресурсы
            if hasattr(self.acc.sip_event_queue, 'current_call'):
                self.acc.sip_event_queue.current_call = None
            Call.current = None
            # Корректно закрываем Deepgram STT сессию
            if self._stt_session:
                self._stt_session.close()
            # Останавливаем фоновый шум
            if self._bg_player:
                try:
                    self._bg_player = None
                except Exception as e:
                    print(f"[PJSUA] Ошибка при освобождении фонового плеера: {e}")
            print("[PJSUA] Вызов завершен и ресурсы освобождены")

        if ci.stateText == "CONFIRMED":
            # Ждём, пока медиа станет активной
            for _ in range(100):
                if hasattr(self, '_audio_media') and self._audio_media is not None:
                    break
                time.sleep(0.05)
            try:
                time.sleep(2)
                wav_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'TEST_fixed.wav'))
                self.play_wav(wav_path)
            except Exception as e:
                print(f"[PJSUA] Ошибка при попытке проиграть аудиофайл: {e}")

    def play_wav(self, wav_path):
        """
        Воспроизведение WAV-файла абоненту
        
        Args:
            wav_path: путь к файлу WAV для воспроизведения
        """
        if not os.path.isfile(wav_path):
            print(f"[PJSUA] Файл для проигрывания не найден: {wav_path}")
            return False
            
        try:
            # Останавливаем предыдущий плеер, если он существует
            if self._player:
                self._player = None
                
            # Создаем новый плеер
            self._player = pj.AudioMediaPlayer()
            self._player.createPlayer(wav_path, pj.PJMEDIA_FILE_NO_LOOP)
            
            # Убеждаемся, что аудио-медиа доступно
            if not self._audio_media:
                self._audio_media = pj.AudioMedia.typecastFromMedia(self.getMedia(0))
                
            # Начинаем передачу аудио
            self._player.startTransmit(self._audio_media)
            print(f"[PJSUA] Проигрывается файл: {wav_path}")
            return True
        except Exception as e:
            print(f"[PJSUA] Ошибка при воспроизведении аудиофайла: {e}")
            return False

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
                # --- Запуск фонового шума ---
                try:
                    bg_wav = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'zvuki-razgovorov-i-raboty-v-ofise.wav'))
                    if os.path.isfile(bg_wav):
                        if self._bg_player:
                            self._bg_player = None
                        self._bg_player = pj.AudioMediaPlayer()
                        self._bg_player.createPlayer(bg_wav, 0)  # 0 = loop
                        if not self._audio_media:
                            self._audio_media = pj.AudioMedia.typecastFromMedia(self.getMedia(mi.index))
                        self._bg_player.startTransmit(self._audio_media)
                        self._bg_player.adjustRxLevel(0.15)  # Тихо
                        print(f"[PJSUA] Фоновый шум запущен: {bg_wav}")
                    else:
                        print(f"[PJSUA] Файл фонового шума не найден: {bg_wav}")
                except Exception as e:
                    print(f"[PJSUA] Ошибка при запуске фонового шума: {e}")

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