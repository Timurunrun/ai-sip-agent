from agents import Agent, Runner
from agents.run import RunConfig
import threading
import logging
import json
from llm.config_llm import SYSTEM_PROMPT, LLM
from crm.crm_api import load_enriched_funnel_config
from crm.status_config import STAGE_STATUS_IDS
from crm.crm_api import AmoCRMClient
from sip.utils import get_active_lead_id
import asyncio
import time
import os

logging.basicConfig(level=logging.INFO)

_llm_agent_instance = None

class LLMAgent:
    def __init__(self, instructions=SYSTEM_PROMPT, model=LLM):
        self.funnel_stages = load_enriched_funnel_config()
        questions = self.get_all_questions()
        questions_text = '\n'.join(f'- {q}' for q in questions) if questions else '- нет вопросов'
        system_prompt = f"{instructions}\n\n[Вопросы для пользователя:]\n{questions_text}"
        self.instructions = system_prompt
        self.model = model
        self.lock = asyncio.Lock()
        self.history = []
        self.llm_busy = False
        self.agent = Agent(
            name="Valentin",
            instructions=self.instructions,
            model=self.model
        )
        logging.info("[LLM] Агент инициализирован")

    def get_all_questions(self):
        questions = []
        for stage in self.funnel_stages:
            for q in stage['questions']:
                questions.append(q.get('name', ''))
        return questions

    def _system_info(self):
        return ''

    async def process_async(self, user_text):
        if self.llm_busy:
            return "[LLM] Пожалуйста, дождитесь ответа на предыдущий вопрос."
        async with self.lock:
            self.llm_busy = True
            try:
                user_message = user_text
                if not self.history:
                    input_data = user_message
                else:
                    input_data = self.history + [{"role": "user", "content": user_message}]
                run_config = RunConfig(tracing_disabled=True)
                try:
                    # --- STREAMING ---
                    result = Runner.run_streamed(self.agent, input_data, run_config=run_config)
                    full_reply = ""
                    async for event in result.stream_events():
                        if event.type == "raw_response_event":
                            data = getattr(event, 'data', None)
                            if data and hasattr(data, 'delta'):
                                print(data.delta, end="", flush=True)  # Реальный вывод токенов
                                full_reply += data.delta
                    # После стрима обновляем историю
                    self.history = result.to_input_list()
                    # Логируем историю диалога
                    log_lines = ["\n========== ТЕКУЩАЯ ИСТОРИЯ ДИАЛОГА =========="]
                    for msg in self.history:
                        role = msg.get('role', 'unknown').upper()
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            content = '\n'.join(str(x) for x in content)
                        content = str(content).strip()
                        log_lines.append(f"[{role}] {content}")
                    log_lines.append("========== КОНЕЦ ИСТОРИИ ==========")
                    logging.info("\n".join(log_lines))
                    return full_reply
                except Exception as e:
                    logging.error(f"[LLM] Ошибка при обработке: {str(e)}", exc_info=True)
                    return f"Произошла ошибка при обработке запроса: {str(e)}"
            finally:
                self.llm_busy = False

    def process(self, user_text):
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if loop and loop.is_running():
            return asyncio.create_task(self.process_async(user_text))
        else:
            return asyncio.run(self.process_async(user_text))

_llm_agent_instance = None

def get_llm_agent():
    global _llm_agent_instance
    if _llm_agent_instance is None:
        _llm_agent_instance = LLMAgent()
    return _llm_agent_instance

async def process_transcript_async(transcript):
    agent = get_llm_agent()
    return await agent.process_async(transcript)

def process_transcript(transcript):
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    if loop and loop.is_running():
        return asyncio.create_task(process_transcript_async(transcript))
    else:
        return asyncio.run(process_transcript_async(transcript))
