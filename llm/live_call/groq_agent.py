import asyncio
import json
import logging
import os
import re
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from groq import Groq
from crm.crm_api import load_enriched_funnel_config
from sip.utils import get_active_lead_id
from tts.elevenlabs_tts import text_to_speech_async

logging.basicConfig(level=logging.INFO)

_llm_agent_instance = None

def load_system_prompt() -> str:
    prompt_file = os.path.join(os.path.dirname(__file__), 'system_prompt.md')

    now_local = datetime.now(timezone.utc)
    weekday_names = [
        "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"
    ]
    current_date_local = now_local.strftime("%Y-%m-%d")
    current_weekday_local = weekday_names[now_local.weekday()]

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            template = f.read().strip()

        system_prompt = (
            template
            .replace('{{CURRENT_DATE_LOCAL}}', current_date_local)
            .replace('{{CURRENT_WEEKDAY_LOCAL}}', current_weekday_local)
        )
        return system_prompt
    except Exception as e:
        logging.error(f"[GROQ] Ошибка загрузки системного промта: {e}")
        return "Твоя задача сказать, что сейчас телефония на техническом обслуживании, пока что пусть пишут в чат или на почту."

def load_system_config() -> dict:
    config_file = os.path.join(os.path.dirname(__file__), 'system_config.json')

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[GROQ] Ошибка загрузки конфигурации: {e}")
    return {}

class GroqAgent:
    def __init__(self):
        self.client = Groq()
        self.funnel_stages = load_enriched_funnel_config()
        
        # Собираем вопросы с примечаниями
        questions_with_comments = self._collect_questions_with_comments()
        questions_text = '\n'.join(f'- {q}' for q in questions_with_comments) if questions_with_comments else 'Нет вопросов'

        self.system_prompt = load_system_prompt()
        self.system_prompt = f"{self.system_prompt}\n\n[ВОПРОСЫ ДЛЯ КЛИЕНТА]\n{questions_text}"

        self.config = load_system_config().get("Groq", {})
        self.model = self.config.get("LLM", "")

        self.tools = [{
            "type": "function",
            "function": {
                "name": "hangup_call",
                "description": "Сбросить текущий телефонный звонок",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Причина завершения звонка",
                        }
                    }
                }
            }
        }]

        self.lock = asyncio.Lock()
        self.llm_busy = False
        self.history_dir = os.path.join(os.path.dirname(__file__), '..', 'dialog_history')
        os.makedirs(self.history_dir, exist_ok=True)
        self.llm_timeout_seconds = self.config.get("timeout_seconds", 7)
        self.timeout_fallback_phrases = self.config.get("timeout_fallback_phrases", [
            "Я прошу прощения, у меня связь прервалась, можете повторить, о чём вы говорили?"
        ])
        logging.info(f"[GROQ] Агент инициализирован с моделью {self.model}")

    def get_all_questions(self) -> List[str]:
        questions = []
        for stage in self.funnel_stages:
            for q in stage['questions']:
                questions.append(q.get('name', ''))
        return questions

    def _collect_questions_with_comments(self) -> List[str]:
        """Возвращает список строк вида 'Название — комментарий' если комментарий есть."""
        lines: List[str] = []
        for stage in self.funnel_stages:
            for q in stage.get('questions', []):
                name = (q.get('name') or '').strip()
                if not name:
                    continue
                comment = (q.get('comment') or '').strip()
                if comment:
                    one_line_comment = ' '.join(comment.split())
                    lines.append(f"{name} — {one_line_comment}")
                else:
                    lines.append(name)
        return lines

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
                full_reply = ""

                loop = asyncio.get_running_loop()

                def _api_call():
                    return self.client.chat.completions.create(
                        model=self.model,
                        messages=groq_messages,
                        tools=self.tools,
                        tool_choice="auto",
                        temperature=self.config.get("temperature", 0.6),
                        reasoning_effort=self.config.get("reasoning_effort", "medium"),
                        max_tokens=self.config.get("max_tokens", 1024)
                    )

                api_future = loop.run_in_executor(None, _api_call)

                try:
                    response = await asyncio.wait_for(api_future, timeout=self.llm_timeout_seconds)
                except asyncio.TimeoutError:
                    fallback = random.choice(self.timeout_fallback_phrases) if self.timeout_fallback_phrases else "Я прошу прощения, у меня связь прервалась, можете повторить, о чём вы говорили?"
                    logging.warning(f"[GROQ] Таймаут {self.llm_timeout_seconds}s — возвращаем fallback: {fallback}")
                    self._send_to_tts_and_play(fallback)
                    history.append({"role": "assistant", "content": fallback})
                    self._save_history(lead_id, history)
                    self._log_conversation_history(history, lead_id)
                    return fallback

                msg = response.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None)

                def _add(m):
                    content = m.content or ""
                    if isinstance(content, str) and content.strip().lower() in {"none", "null"}:
                        content = ""
                    if getattr(m, "role", "") == "assistant":
                        content = self._sanitize_model_output(content)
                    history.append({"role": m.role, "content": content})

                if tool_calls:
                    _add(msg)
                    for tc in tool_calls:
                        if tc.function.name == "hangup_call":
                            args = json.loads(tc.function.arguments or "{}")
                            reason = args.get("reason", "")
                            speak_text = self._sanitize_model_output(msg.content or "")

                            from sip.command_queue import queue_command

                            if not speak_text:
                                # Fallback-фраза, если модель не дала текста
                                speak_text = "Спасибо за звонок, всего доброго, до свидания."

                            # Озвучиваем и после воспроизведения завершаем
                            self._send_to_tts_and_play(speak_text)
                            queue_command("hangup_after_playback", reason=reason, immediate=False)
                            full_reply = speak_text

                            history.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": "hangup_call",
                                "content": "OK"
                            })
                else:
                    full_reply = msg.content or ""
                    speak_text = self._sanitize_model_output(full_reply)
                    if speak_text:
                        self._send_to_tts_and_play(speak_text)
                    _add(msg)

                self._save_history(lead_id, history)
                self._log_conversation_history(history, lead_id)
                return full_reply
                    
            except Exception as e:
                logging.error(f"[GROQ] Ошибка при обращении к API: {str(e)}", exc_info=True)
                
            finally:
                self.llm_busy = False

    @staticmethod
    def _sanitize_model_output(text: str) -> str:
        """
        Удаляет размышления reasoning-моделей (блоки <think>...</think>)
        перед передачей в TTS.
        """
        if not text:
            return text
        # Убираем теги <think>...</think>
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        # Убираем лишние пробелы/переводы строк
        cleaned = cleaned.strip()
        return cleaned

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

    @staticmethod
    def _hangup_call(reason: str = ""):
        """Помещает команду завершения вызова после воспроизведения аудио."""
        from sip.command_queue import queue_command
        queue_command("hangup_after_playback", reason=reason)

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
