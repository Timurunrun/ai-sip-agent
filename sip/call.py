import threading
import os
import time
import wave
import pjsua2 as pj
from stt.deepgram_stt import DeepgramSTTSession


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
        self._current_audio_duration = 0
        self._greeting_played = False
        self._greeting_pending = False
        self._greeting_ready_at = 0.0

        self._pending_hangup = False
        self._pending_hangup_waiting_start = False
        self._pending_hangup_requested_at = 0.0
        self._pending_hangup_reason = ""
        self._pending_hangup_start_timeout = 8.0

        # Не помечаем звонок глобально активным до фактического принятия

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
            
            # Запускаем пост-обработку звонка
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
                # Планируем приветствие с задержкой (2 секунды) — выполняем потом в основном цикле
                if not self._greeting_played and not self._greeting_pending:
                    self._greeting_pending = True
                    self._greeting_ready_at = time.time() + 2.0
                    print("[AUDIO] Приветствие запланировано (через 2 сек)")

    def connect_stt_session(self, filename):
        self._recording_filename = filename
        self._stt_session = DeepgramSTTSession(filename)

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
        Проверяет естественное окончание воспроизведения и управляет отложенным завершением вызова.
        Должен вызываться из основного потока.
        """
        try:
            # Приветствие
            if self._greeting_pending and not self._greeting_played and time.time() >= self._greeting_ready_at:
                try:
                    greeting_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'audio', 'opening.wav'))
                    if os.path.exists(greeting_path):
                        played = self.play_audio_file(greeting_path)
                        if played:
                            print(f"[AUDIO] Приветствие проигрывается: {greeting_path}")
                            self._greeting_played = True
                        else:
                            print(f"[AUDIO] Не удалось начать воспроизведение приветствия: {greeting_path}")
                    else:
                        print(f"[AUDIO] Файл приветствия не найден: {greeting_path}")
                    self._greeting_pending = False
                except Exception as e:
                    print(f"[AUDIO] Ошибка при запуске приветствия: {e}")
                    self._greeting_pending = False

            # Контроль активного воспроизведения
            if self._player and self._player_start_time > 0:
                elapsed_time = time.time() - self._player_start_time
                if (self._current_audio_duration > 0 and elapsed_time >= self._current_audio_duration + 0.5):
                    print(f"[AUDIO] Воспроизведение завершено ({self._current_audio_duration:.1f}с)")
                    self.stop_audio_playback()
                elif elapsed_time > self._max_playback_duration:
                    print(f"[AUDIO] Принудительная остановка по таймауту ({self._max_playback_duration}с)")
                    self.stop_audio_playback()

            if self._pending_hangup:
                now = time.time()
                if self._pending_hangup_waiting_start:
                    # Ждём появления плеера
                    if self._player:
                        self._pending_hangup_waiting_start = False
                        print(f"[CALL] Прощальное воспроизведение началось, ждём окончания для завершения ({self._pending_hangup_reason})")
                    elif now - self._pending_hangup_requested_at > self._pending_hangup_start_timeout:
                        # Плеер так и не появился — завершаем, чтобы не висеть бесконечно
                        print(f"[CALL] Таймаут ожидания старта прощальной фразы, завершаем вызов ({self._pending_hangup_reason})")
                        self._execute_hangup()
                else:
                    # Ожидаем окончания текущего или уже завершившегося воспроизведения
                    if not self._player:
                        self._execute_hangup()
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
            # Остановка предыдущего плеера, если он есть
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

            # Сначала запускаем передачу от плеера к медиа
            self._player.startTransmit(self._audio_media)
            self._player_start_time = time.time()  # Запоминаем время начала
            
            # Если мы ждали старта прощального воспроизведения, фиксируем переход
            if self._pending_hangup and self._pending_hangup_waiting_start:
                self._pending_hangup_waiting_start = False
                print(f"[CALL] Прощальное воспроизведение стартовало ({self._pending_hangup_reason})")

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
            # Сначала остановка передачи, потом очистка
            if self._audio_media:
                self._player.stopTransmit(self._audio_media)
            self._player = None
            self._player_start_time = 0
            self._current_audio_duration = 0
            print("[AUDIO] Воспроизведение остановлено")
            return True
        except Exception as e:
            print(f"[AUDIO] Ошибка при остановке воспроизведения: {e}")
            self._player = None
            self._player_start_time = 0
            self._current_audio_duration = 0
            return False

    def request_hangup_after_playback(self, reason: str = "", immediate: bool = False, expect_future_playback: bool = True):
        """Запрашивает плавное завершение вызова после прощальной фразы.

        Args:
            reason: Причина завершения
            immediate: Если True и нет активного плеера — завершить немедленно
            expect_future_playback: Если True и сейчас нет плеера — подождать запуска будущего (процесс TTS)
        """
        self._pending_hangup_reason = reason or self._pending_hangup_reason

        # Если уже запрошено завершение
        if self._pending_hangup:
            if immediate and not self._player and not self._pending_hangup_waiting_start:
                self._execute_hangup()
            return

        if self._player:
            # Идёт воспроизведение, дождёмся его конца
            self._pending_hangup = True
            self._pending_hangup_waiting_start = False
            self._pending_hangup_requested_at = time.time()
            print(f"[CALL] Запрошено завершение после текущего воспроизведения ({self._pending_hangup_reason})")
            return

        if immediate and not expect_future_playback:
            print(f"[CALL] Немедленное завершение без воспроизведения ({self._pending_hangup_reason})")
            self._execute_hangup()
            return

        if expect_future_playback:
            # Ждём появления аудио на прощание
            self._pending_hangup = True
            self._pending_hangup_waiting_start = True
            self._pending_hangup_requested_at = time.time()
            print(f"[CALL] Запрошено завершение: ждём старта прощальной фразы ({self._pending_hangup_reason})")
        else:
            # Ожидать нечего, завершаем немедленно
            print(f"[CALL] Завершение без ожидания воспроизведения ({self._pending_hangup_reason})")
            self._execute_hangup()

    def _execute_hangup(self):
        """Выполняет фактический hangup и сбрасывает флаги."""
        try:
            import pjsua2 as pj
            prm = pj.CallOpParam()
            self.hangup(prm)
            print(f"[CALL] Завершение вызова выполнено ({self._pending_hangup_reason})")
        except Exception as e:
            print(f"[CALL] Ошибка при завершении вызова: {e}")
        finally:
            self._pending_hangup = False
            self._pending_hangup_waiting_start = False
            self._pending_hangup_requested_at = 0.0
            self._pending_hangup_reason = ""

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
                try:
                    self._stt_session.connect()
                except Exception:
                    pass
                self._stt_session.start_streaming()
            
        except Exception as e:
            print(f"[PJSUA] Ошибка при инициализации аудио: {e}")
            return

    def _start_post_call_processing(self):
        """Запускает пост-обработку завершенного звонка"""
        try:
            # Проверяем наличие ID лида
            if not hasattr(self, 'lead_id') or not self.lead_id:
                print("[POST_PROCESSOR] Нет ID лида для пост-обработки")
                return
            
            # Загружаем историю диалога
            from llm.live_call import get_llm_agent
            agent = get_llm_agent()
            history = agent._load_history(self.lead_id)
            
            if not history:
                print(f"[POST_PROCESSOR] Нет истории для лида {self.lead_id}")
                return
            
            # Запускаем пост-обработку
            from llm.post_processing.post_processor import process_call_end
            process_call_end(self.lead_id, history)
            print(f"[POST_PROCESSOR] пост-обработка запущена для лида {self.lead_id}")
            
        except Exception as e:
            print(f"[POST_PROCESSOR] Ошибка запуска пост-обработки: {e}")
