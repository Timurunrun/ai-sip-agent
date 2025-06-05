import threading
import os
import time
import wave
import pjsua2 as pj
from stt.deepgram_stt import stt_from_wav, DeepgramSTTSession
from sip.utils import get_active_lead_id

class Call(pj.Call):
    current = None
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
        self._player_start_time = 0
        self._max_playback_duration = 30
        self._current_audio_duration = 0  # Длительность текущего файла
        Call.current = self

    def onCallState(self, prm):
        ci = self.getInfo()
        print(f"[PJSUA] Состояние вызова: {ci.stateText}, Код: {ci.lastStatusCode}")
        
        if ci.stateText == "DISCONNECTED":
            self.connected = False
            self.stop_streaming.set()
            try:
                if self._audio_media and self._recorder:
                    for mi in ci.media:
                        if (mi.type == pj.PJMEDIA_TYPE_AUDIO and 
                            mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE):
                            self._audio_media.stopTransmit(self._recorder)
                            break
            except Exception as e:
                print(f"[PJSUA] Ошибка при остановке аудио: {e}")
            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=1.0)
            try:
                if self._recorder:
                    self._recorder = None
                if self._audio_media:
                    self._audio_media = None
                if self._player:
                    try:
                        # Сначала останавливаем передачу, затем очищаем плеер
                        if hasattr(self, '_audio_media') and self._audio_media:
                            self._player.stopTransmit(self._audio_media)
                        self._player = None
                        self._player_start_time = 0
                        self._current_audio_duration = 0
                    except Exception as e:
                        print(f"[PJSUA] Ошибка при освобождении плеера: {e}")
                        self._player = None  # Принудительно очищаем
                        self._player_start_time = 0
                        self._current_audio_duration = 0
            except Exception as e:
                print(f"[PJSUA] Ошибка при освобождении медиа ресурсов: {e}")
            if hasattr(self.acc.sip_event_queue, 'current_call'):
                self.acc.sip_event_queue.current_call = None
            Call.current = None
            if self._stt_session:
                self._stt_session.close()
            
            # Запускаем постобработку звонка
            self._start_post_call_processing()
            
            print("[PJSUA] Вызов завершен и ресурсы освобождены")

        if ci.stateText == "CONFIRMED":
            for _ in range(100):
                if hasattr(self, '_audio_media') and self._audio_media is not None:
                    break
                time.sleep(0.05)
            print("[PJSUA] Соединение установлено!")

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

    def _get_audio_duration(self, audio_file_path):
        try:
            with wave.open(audio_file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                duration = frames / float(sample_rate)
                return duration
        except Exception as e:
            print(f"[AUDIO] Не удалось определить длительность файла {audio_file_path}: {e}")
            return 0

    def check_pending_audio(self):
        """
        Проверяет естественное окончание воспроизведения.
        Должен вызываться из основного потока.
        """
        try:
            # Проверка окончания воспроизведения
            if (self._player and self._player_start_time > 0):
                elapsed_time = time.time() - self._player_start_time
                
                # Сначала проверяем естественное окончание по длительности файла
                if (self._current_audio_duration > 0 and 
                    elapsed_time >= self._current_audio_duration + 0.5):  # +0.5с буфер
                    print(f"[AUDIO] Воспроизведение завершено естественным образом ({self._current_audio_duration:.1f}с)")
                    self.stop_audio_playback()
                # Затем проверяем таймаут как запасной вариант
                elif elapsed_time > self._max_playback_duration:
                    print(f"[AUDIO] Принудительная остановка воспроизведения по таймауту ({self._max_playback_duration}с)")
                    self.stop_audio_playback()
                
        except Exception as e:
            print(f"[AUDIO] Ошибка в check_pending_audio: {e}")

    def play_audio_file(self, audio_file_path, loop=False):
        """
        Универсальный метод для воспроизведения аудиофайла абоненту.

        Args:
            audio_file_path (str): Путь к аудиофайлу
            loop (bool): Зацикливать ли воспроизведение
            
        Returns:
            bool: True если воспроизведение началось успешно, False в противном случае
        """
        # Проверка наличия активного медиа-канала
        if not self._audio_media:
            print(f"[AUDIO] Медиа канал недоступен для воспроизведения {audio_file_path}")
            return False
            
        # Проверка существования файла
        if not os.path.exists(audio_file_path):
            print(f"[AUDIO] Файл не найден: {audio_file_path}")
            return False
            
        try:
            # Остановка предыдущего плеера если он есть
            if self._player:
                try:
                    self._player.stopTransmit(self._audio_media)
                    self._player = None
                    # Небольшая пауза для стабилизации медиа потока
                    time.sleep(0.01)
                except Exception as e:
                    print(f"[AUDIO] Предупреждение при остановке предыдущего плеера: {e}")
            
            # Определяем длительность файла перед воспроизведением
            self._current_audio_duration = self._get_audio_duration(audio_file_path)
            
            # Создание и запуск нового плеера
            self._player = pj.AudioMediaPlayer()
            self._player.createPlayer(audio_file_path, pj.PJMEDIA_FILE_NO_LOOP if not loop else 0)
            
            # Правильная последовательность: сначала запускаем передачу от плеера к медиа
            self._player.startTransmit(self._audio_media)
            self._player_start_time = time.time()  # Запоминаем время начала
            
            duration_info = f" (длительность: {self._current_audio_duration:.1f}с)" if self._current_audio_duration > 0 else ""
            print(f"[AUDIO] Воспроизведение началось: {os.path.basename(audio_file_path)}{duration_info}")
            return True
            
        except Exception as e:
            print(f"[AUDIO] Ошибка воспроизведения {audio_file_path}: {e}")
            self._player = None
            return False

    def stop_audio_playback(self):
        """
        Останавливает текущее воспроизведение аудио.
        
        Returns:
            bool: True если остановка прошла успешно, False в противном случае
        """
        if not self._player:
            return True
            
        try:
            # Правильная последовательность: сначала остановка передачи, потом очистка
            if self._audio_media:
                self._player.stopTransmit(self._audio_media)
            self._player = None
            self._player_start_time = 0  # Сбрасываем время
            self._current_audio_duration = 0  # Сбрасываем длительность
            print("[AUDIO] Воспроизведение остановлено")
            return True
        except Exception as e:
            print(f"[AUDIO] Ошибка при остановке воспроизведения: {e}")
            self._player = None  # Принудительно очищаем даже при ошибке
            self._player_start_time = 0
            self._current_audio_duration = 0
            return False

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
            if self._stt_session:
                self._stt_session.start_streaming()
            
        except Exception as e:
            print(f"[PJSUA] Ошибка при инициализации аудио: {e}")
            return

    def _start_post_call_processing(self):
        """Запускает постобработку завершенного звонка"""
        try:
            # Проверяем наличие ID лида
            if not hasattr(self, 'lead_id') or not self.lead_id:
                print("[POST_PROCESSOR] Нет ID лида для постобработки")
                return
            
            # Загружаем историю диалога
            from llm.groq_agent import get_llm_agent
            agent = get_llm_agent()
            history = agent._load_history(self.lead_id)
            
            if not history:
                print(f"[POST_PROCESSOR] Нет истории для лида {self.lead_id}")
                return
            
            # Запускаем постобработку
            from llm.post_call_processor import process_call_end
            process_call_end(self.lead_id, history)
            print(f"[POST_PROCESSOR] Постобработка запущена для лида {self.lead_id}")
            
        except Exception as e:
            print(f"[POST_PROCESSOR] Ошибка запуска постобработки: {e}")