"""
Утилиты для работы с аудиоплеером PJSUA.

Этот модуль содержит удобные функции для воспроизведения аудиофайлов
через активный звонок в системе PJSUA.
"""

import os
import logging
import queue
import threading
from .call import Call

# Глобальная очередь для безопасной передачи аудиофайлов между потоками
_audio_queue = queue.Queue()
_queue_lock = threading.Lock()


def queue_audio_for_playback(audio_file_path):
    """
    Добавляет аудиофайл в очередь для воспроизведения.
    Безопасно вызывать из любого потока.
    
    Args:
        audio_file_path (str): Путь к аудиофайлу
    """
    try:
        _audio_queue.put(audio_file_path, block=False)
        logging.info(f"[AUDIO] Файл добавлен в очередь: {os.path.basename(audio_file_path)}")
    except queue.Full:
        logging.error("[AUDIO] Очередь воспроизведения переполнена")


def process_audio_queue():
    """
    Обрабатывает очередь аудиофайлов для воспроизведения.
    ДОЛЖНА вызываться только из основного потока PJSUA!
    
    Returns:
        bool: True если был обработан хотя бы один файл
    """
    processed = False
    
    try:
        while not _audio_queue.empty():
            try:
                audio_file_path = _audio_queue.get_nowait()
                success = play_audio_to_current_call(audio_file_path)
                if success:
                    logging.info(f"[AUDIO] Воспроизведение началось: {os.path.basename(audio_file_path)}")
                    processed = True
                else:
                    logging.error(f"[AUDIO] Не удалось воспроизвести: {audio_file_path}")
                _audio_queue.task_done()
            except queue.Empty:
                break
    except Exception as e:
        logging.error(f"[AUDIO] Ошибка при обработке очереди: {e}")
    
    return processed


def play_audio_to_current_call(audio_file_path, loop=False):
    """
    Воспроизводит аудиофайл в текущий активный звонок.
    
    Args:
        audio_file_path (str): Путь к аудиофайлу
        loop (bool): Зацикливать ли воспроизведение
        
    Returns:
        bool: True если воспроизведение началось успешно, False в противном случае
    """
    current_call = Call.current
    if not current_call:
        logging.warning("[AUDIO] Нет активного звонка для воспроизведения аудио")
        return False
        
    return current_call.play_audio_file(audio_file_path, loop)


def stop_current_call_audio():
    """
    Останавливает воспроизведение аудио в текущем активном звонке.
    
    Returns:
        bool: True если остановка прошла успешно, False в противном случае
    """
    current_call = Call.current
    if not current_call:
        return True
        
    return current_call.stop_audio_playback()


def play_welcome_message():
    """
    Воспроизводит приветственное сообщение в текущий звонок.
    
    Returns:
        bool: True если воспроизведение началось успешно, False в противном случае
    """
    welcome_file = os.path.join(os.path.dirname(__file__), '..', 'ElevenLabs_Text_to_Speech_audio.wav')
    return play_audio_to_current_call(welcome_file)


def get_audio_file_path(filename):
    """
    Получает полный путь к аудиофайлу относительно корня проекта.
    
    Args:
        filename (str): Имя файла
        
    Returns:
        str: Полный путь к файлу
    """
    return os.path.join(os.path.dirname(__file__), '..', filename)
