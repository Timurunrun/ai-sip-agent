import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from openai import OpenAI
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
        logging.error(f"[OpenAI] Ошибка загрузки системного промта: {e}")
        return "Твоя задача сказать, что сейчас телефония на техническом обслуживании, пока что пусть пишут в чат или на почту."


def load_system_config() -> dict:
    config_file = os.path.join(os.path.dirname(__file__), 'system_config.json')

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[OpenAI] Ошибка загрузки конфигурации: {e}")
    return {}


class OpenAIAgent:
    """Агент для живого звонка, адаптированный под API OpenAI."""

    def __init__(self):
        self.client = OpenAI()
        self.funnel_stages = load_enriched_funnel_config()
        questions = self.get_all_questions()
        questions_text = '\n'.join(f'- {q}' for q in questions) if questions else 'Нет вопросов'

        self.system_prompt = load_system_prompt()
        self.system_prompt = f"{self.system_prompt}\n\n[ВОПРОСЫ ДЛЯ КЛИЕНТА]\n{questions_text}"

        self.config = load_system_config().get("OpenAI", {})
        self.model = self.config.get("LLM", "gpt-5")

        # Инструменты (функции) для OpenAI
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "hangup_call",
                    "description": "Сбросить текущий телефонный звонок",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "Причина завершения звонка"
                            }
                        }
                    }
                }
            }
        ]

        self.lock = asyncio.Lock()
        self.llm_busy = False
        self.history_dir = os.path.join(os.path.dirname(__file__), '..', 'dialog_history')
        os.makedirs(self.history_dir, exist_ok=True)
        logging.info(f"[OpenAI] Агент инициализирован с моделью {self.model}")

    # ========================= История =========================
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
                logging.info(f"[OpenAI] Загружена история для лида {lead_id}: {len(history)} сообщений")
                return history
        except Exception as e:
            logging.error(f"[OpenAI] Ошибка загрузки истории для лида {lead_id}: {e}")
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
                logging.info(f"[OpenAI] Сохранена история для лида {lead_id}: {len(history)} сообщений")
        except Exception as e:
            logging.error(f"[OpenAI] Ошибка сохранения истории для лида {lead_id}: {e}")

    def _format_history_for_openai(self, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Преобразует локальную историю в формат OpenAI, сохраняя tool-взаимодействия.

        Поддерживаются роли:
        - system (добавляется один раз в начале)
        - user
        - assistant (включая tool_calls, если сохранены)
        - tool (ответы инструментов: содержат tool_call_id)

        Старые записи без tool_calls остаются валидными.
        """
        openai_messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        for msg in history:
            role = (msg.get('role') or '').lower()
            if role not in {"user", "assistant", "tool"}:
                continue
            content = (msg.get('content') or '').strip()
            if not content and role != 'assistant':  # пустые user/tool сообщения пропускаем
                continue
            if role == 'assistant':
                m: Dict[str, Any] = {"role": "assistant", "content": content}
                # если когда-то сохранили tool_calls
                if 'tool_calls' in msg and isinstance(msg['tool_calls'], list) and msg['tool_calls']:
                    m['tool_calls'] = msg['tool_calls']
                openai_messages.append(m)
            elif role == 'user':
                openai_messages.append({"role": "user", "content": content})
            elif role == 'tool':
                # Сообщение-инструмент. API ожидает tool_call_id и content.
                tool_call_id = msg.get('tool_call_id') or msg.get('id') or ''
                if tool_call_id:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": content
                    })
        return openai_messages

    # ========================= LLM =========================
    async def process_async(self, user_text: str) -> str:
        if self.llm_busy:
            return "[OpenAI] Пожалуйста, дождитесь ответа на предыдущий вопрос."

        lead_id = get_active_lead_id()
        if not lead_id:
            logging.warning("[OpenAI] Не удалось получить ID активного лида")

        async with self.lock:
            self.llm_busy = True
            try:
                history = self._load_history(lead_id) if lead_id else []
                history.append({"role": "user", "content": user_text})
                openai_messages = self._format_history_for_openai(history)
                full_reply = ""
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=openai_messages,
                    tools=self.tools,
                    tool_choice="auto",
                    reasoning={"effort": self.config.get("reasoning", "medium")},
                )

                msg = response.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None)

                def _add(m):
                    content = m.content or ""
                    if isinstance(content, str) and content.strip().lower() in {"none", "null"}:
                        content = ""
                    record: Dict[str, Any] = {"role": m.role, "content": content}
                    # Сохраняем tool_calls ассистента для восстановления контекста
                    tc_list = getattr(m, 'tool_calls', None)
                    if tc_list:
                        serialized = []
                        for tc in tc_list:
                            try:
                                serialized.append({
                                    "id": getattr(tc, 'id', None),
                                    "type": getattr(tc, 'type', None),
                                    "function": {
                                        "name": getattr(getattr(tc, 'function', None), 'name', None),
                                        "arguments": getattr(getattr(tc, 'function', None), 'arguments', None),
                                    }
                                })
                            except Exception:
                                pass
                        if serialized:
                            record['tool_calls'] = serialized
                    history.append(record)

                if tool_calls:
                    _add(msg)
                    for tc in tool_calls:
                        if tc.function.name == "hangup_call":
                            args = json.loads(tc.function.arguments or "{}")
                            reason = args.get("reason", "")
                            speak_text = msg.content or ""
                            from sip.command_queue import queue_command
                            if not speak_text:
                                speak_text = "Спасибо за звонок, всего доброго, до свидания."
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
                    speak_text = full_reply
                    if speak_text:
                        self._send_to_tts_and_play(speak_text)
                    _add(msg)

                self._save_history(lead_id, history)
                self._log_conversation_history(history, lead_id)
                return full_reply
            except Exception as e:
                logging.error(f"[OpenAI] Ошибка при обращении к API: {str(e)}", exc_info=True)
            finally:
                self.llm_busy = False

    # ========================= Утилиты =========================

    def _log_conversation_history(self, history: List[Dict[str, Any]], lead_id: Optional[str]) -> None:
        log_lines = [f"\n========== ИСТОРИЯ ДИАЛОГА ЛИДА {lead_id or 'UNKNOWN'} =========="]
        for msg in history:
            role = msg.get('role', 'unknown').upper()
            content = str(msg.get('content', '')).strip()
            log_lines.append(f"[{role}] {content}")
        log_lines.append("========== КОНЕЦ ИСТОРИИ ==========")
        logging.info("\n".join(log_lines))

    def _send_to_tts_and_play(self, text: str) -> None:
        logging.info(f"[OpenAI->TTS] Отправляем в TTS: {text}")

        def tts_callback(audio_filepath: Optional[str]) -> None:
            if audio_filepath and os.path.exists(audio_filepath):
                logging.info(f"[TTS] Аудиофайл готов: {audio_filepath}")
                from sip.audio_player import queue_audio_for_playback
                queue_audio_for_playback(audio_filepath)
                logging.info(f"[TTS] Файл добавлен в очередь: {os.path.basename(audio_filepath)}")
            else:
                logging.error("[TTS] Не удалось создать аудиофайл")

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
        from sip.command_queue import queue_command
        queue_command("hangup_after_playback", reason=reason)


# ========================= Глобальные функции =========================
_llm_agent_instance = None


def get_llm_agent():
    global _llm_agent_instance
    if _llm_agent_instance is None:
        _llm_agent_instance = OpenAIAgent()
    return _llm_agent_instance


async def process_transcript_async(transcript: str) -> str:
    agent = get_llm_agent()
    return await agent.process_async(transcript)


def process_transcript(transcript: str):
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    if loop and loop.is_running():
        return asyncio.create_task(process_transcript_async(transcript))
    else:
        return asyncio.run(process_transcript_async(transcript))
