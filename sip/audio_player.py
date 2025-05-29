"""
Утилиты для работы с аудиоплеером PJSUA.

Этот модуль содержит удобные функции для воспроизведения аудиофайлов
через активный звонок в системе PJSUA.
"""

import os
import logging
from .call import Call


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
