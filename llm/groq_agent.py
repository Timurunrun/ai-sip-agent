import asyncio
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional

from groq import Groq
from llm.config_llm import SYSTEM_PROMPT, LLM
from crm.crm_api import load_enriched_funnel_config
from sip.utils import get_active_lead_id
from tts.elevenlabs_tts import text_to_speech_async

logging.basicConfig(level=logging.INFO)

_llm_agent_instance = None

class GroqAgent:
    def __init__(self, instructions=SYSTEM_PROMPT, model=LLM):
        self.client = Groq()
        self.funnel_stages = load_enriched_funnel_config()
        questions = self.get_all_questions()
        questions_text = '\n'.join(f'- {q}' for q in questions) if questions else '- нет вопросов'
        self.system_prompt = f"{instructions}\n\n[Вопросы для пользователя:]\n{questions_text}"
        self.model = model
        self.lock = asyncio.Lock()
        self.llm_busy = False
        self.history_dir = os.path.join(os.path.dirname(__file__), '..', 'dialog_history')
        os.makedirs(self.history_dir, exist_ok=True)
        logging.info(f"[GROQ] Агент инициализирован с моделью {self.model}")

    def get_all_questions(self) -> List[str]:
        questions = []
        for stage in self.funnel_stages:
            for q in stage['questions']:
                questions.append(q.get('name', ''))
        return questions

    def _get_history_file_path(self, lead_id: Optional[str]) -> Optional[str]:
        if not lead_id:
            return None
        return os.path.join(self.history_dir, f"lead_{lead_id}_history.json")

    def _load_history(self, lead_id: Optional[str]) -> List[Dict[str, Any]]:
        if not lead_id:
            return []
        
        history_file = self._get_history_file_path(lead_id)
        if not history_file or not os.path.exists(history_file):
            return []
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                logging.info(f"[GROQ] Загружена история для лида {lead_id}: {len(history)} сообщений")
                return history
        except Exception as e:
            logging.error(f"[GROQ] Ошибка загрузки истории для лида {lead_id}: {e}")
            return []

    def _save_history(self, lead_id: Optional[str], history: List[Dict[str, Any]]) -> None:
        if not lead_id:
            return
        
        history_file = self._get_history_file_path(lead_id)
        if not history_file:
            return
            
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                logging.info(f"[GROQ] Сохранена история для лида {lead_id}: {len(history)} сообщений")
        except Exception as e:
            logging.error(f"[GROQ] Ошибка сохранения истории для лида {lead_id}: {e}")

    def _format_history_for_groq(self, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        groq_messages = [{"role": "system", "content": self.system_prompt}]
        
        for msg in history:
            role = msg.get('role', '').lower()
            content = str(msg.get('content', '')).strip()
            
            if role in ['user', 'assistant'] and content:
                groq_messages.append({"role": role, "content": content})
        
        return groq_messages

    async def process_async(self, user_text: str) -> str:
        if self.llm_busy:
            return "[GROQ] Пожалуйста, дождитесь ответа на предыдущий вопрос."
        
        lead_id = get_active_lead_id()
        if not lead_id:
            logging.warning("[GROQ] Не удалось получить ID активного лида")
        
        async with self.lock:
            self.llm_busy = True
            try:
                history = self._load_history(lead_id) if lead_id else []
                history.append({"role": "user", "content": user_text})
                groq_messages = self._format_history_for_groq(history)
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=groq_messages,
                        temperature=0.7,
                        max_tokens=1024
                    )
                    
                    full_reply = response.choices[0].message.content
                    
                    # Отправляем реплику в TTS и на воспроизведение
                    self._send_to_tts_and_play(full_reply)
                    
                    history.append({"role": "assistant", "content": full_reply})
                    self._save_history(lead_id, history)
                    self._log_conversation_history(history, lead_id)
                    
                    return full_reply
                    
                except Exception as e:
                    logging.error(f"[GROQ] Ошибка при обращении к API: {str(e)}", exc_info=True)
                    return f"Произошла ошибка при обработке запроса: {str(e)}"
                    
            finally:
                self.llm_busy = False

    def _log_conversation_history(self, history: List[Dict[str, Any]], lead_id: Optional[str]) -> None:
        log_lines = [f"\n========== ИСТОРИЯ ДИАЛОГА ЛИДА {lead_id or 'UNKNOWN'} =========="]
        for msg in history:
            role = msg.get('role', 'unknown').upper()
            content = str(msg.get('content', '')).strip()
            log_lines.append(f"[{role}] {content}")
        log_lines.append("========== КОНЕЦ ИСТОРИИ ==========")
        logging.info("\n".join(log_lines))

    def _send_to_tts_and_play(self, text: str) -> None:
        """
        Отправляет текст в TTS и добавляет аудиофайл в очередь для воспроизведения
        """
        logging.info(f"[GROQ->TTS] Отправляем в TTS: {text}")
        
        def tts_callback(audio_filepath: Optional[str]) -> None:
            if audio_filepath and os.path.exists(audio_filepath):
                logging.info(f"[TTS] Аудиофайл готов: {audio_filepath}")
                # Добавляем файл в очередь воспроизведения (безопасно из любого потока)
                from sip.audio_player import queue_audio_for_playback
                queue_audio_for_playback(audio_filepath)
                logging.info(f"[TTS] Файл добавлен в очередь: {os.path.basename(audio_filepath)}")
            else:
                logging.error("[TTS] Не удалось создать аудиофайл")
        
        # Асинхронно создаем аудио и добавляем в очередь
        text_to_speech_async(text, tts_callback)

    def process(self, user_text: str):
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
            
        if loop and loop.is_running():
            return asyncio.create_task(self.process_async(user_text))
        else:
            return asyncio.run(self.process_async(user_text))


# Глобальные функции для совместимости
_llm_agent_instance = None

def get_llm_agent():
    """Получает глобальный экземпляр GroqAgent"""
    global _llm_agent_instance
    if _llm_agent_instance is None:
        _llm_agent_instance = GroqAgent()
    return _llm_agent_instance

async def process_transcript_async(transcript: str) -> str:
    """Асинхронная обработка транскрипта"""
    agent = get_llm_agent()
    return await agent.process_async(transcript)

def process_transcript(transcript: str):
    """Синхронная обработка транскрипта"""
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
        
    if loop and loop.is_running():
        return asyncio.create_task(process_transcript_async(transcript))
    else:
        return asyncio.run(process_transcript_async(transcript))
