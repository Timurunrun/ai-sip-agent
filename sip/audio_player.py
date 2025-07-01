"""
Утилиты для работы с аудиоплеером PJSUA.

Этот модуль содержит удобные функции для воспроизведения аудиофайлов
через активный звонок в системе PJSUA.
"""

import os
import logging
import queue
from .call import Call


def queue_audio_for_playback(call: Call, audio_file_path: str):
    """Добавляет аудиофайл в очередь конкретного звонка."""
    try:
        call.audio_queue.put(audio_file_path, block=False)
        logging.info(
            f"[AUDIO] Файл добавлен в очередь: {os.path.basename(audio_file_path)}"
        )
    except queue.Full:
        logging.error("[AUDIO] Очередь воспроизведения переполнена")


def process_audio_queue(call: Call):
    """Обрабатывает очередь аудиофайлов конкретного звонка."""
    processed = False

    try:
        while not call.audio_queue.empty():
            try:
                audio_file_path = call.audio_queue.get_nowait()
                success = call.play_audio_file(audio_file_path)
                if success:
                    logging.info(
                        f"[AUDIO] Воспроизведение началось: {os.path.basename(audio_file_path)}"
                    )
                    processed = True
                else:
                    logging.error(
                        f"[AUDIO] Не удалось воспроизвести: {audio_file_path}"
                    )
                call.audio_queue.task_done()
            except queue.Empty:
                break
    except Exception as e:
        logging.error(f"[AUDIO] Ошибка при обработке очереди: {e}")

    return processed


def play_audio_to_call(call: Call, audio_file_path: str, loop: bool = False) -> bool:
    """Воспроизводит аудиофайл в указанный звонок."""
    return call.play_audio_file(audio_file_path, loop)


def stop_call_audio(call: Call) -> bool:
    """Останавливает воспроизведение аудио в указанном звонке."""
    return call.stop_audio_playback()


def play_welcome_message(call: Call) -> bool:
    """Воспроизводит приветственное сообщение в указанный звонок."""
    welcome_file = os.path.join(
        os.path.dirname(__file__), "..", "ElevenLabs_Text_to_Speech_audio.wav"
    )
    return play_audio_to_call(call, welcome_file)


def get_audio_file_path(filename):
    """
    Получает полный путь к аудиофайлу относительно корня проекта.
    
    Args:
        filename (str): Имя файла
        
    Returns:
        str: Полный путь к файлу
    """
    return os.path.join(os.path.dirname(__file__), '..', filename)
