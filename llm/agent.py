from agents import Agent, Runner
from agents.run import RunConfig
import threading
import logging
import json
from llm.config_llm import SYSTEM_PROMPT, LLM
from crm.crm_api import load_enriched_funnel_config
from llm.tools import fill_crm_field, skip_crm_field, set_remove_question_callback
from crm.status_config import STAGE_STATUS_IDS
from crm.crm_api import AmoCRMClient
from sip.utils import get_active_lead_id
import weave
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor
from agents import set_trace_processors
import asyncio

# Инициализация Weave
weave.init("pjsua-agent-tracing")
set_trace_processors([WeaveTracingProcessor()])

# Настройка детального логирования
logging.basicConfig(level=logging.INFO)

class LLMAgent:
    def __init__(self, instructions=SYSTEM_PROMPT, model=LLM):
        self.instructions = instructions
        self.model = model
        self.lock = asyncio.Lock()  # асинхронный lock
        self.history = []  # Список сообщений для контекста
        self.stage_idx = 0
        self.llm_busy = False  # Флаг занятости LLM
        
        # Хранение информации о вопросах
        self.answered_fields = {}  # {field_id: {"value": value, "type": type}}
        
        # Загружаем enriched funnel config из кеша
        self.funnel_stages = load_enriched_funnel_config()
        
        # Устанавливаем callback для инструментов
        set_remove_question_callback(self._mark_field_answered)
        
        # Создаем агента с инструментами
        self.agent = Agent(
            name="Valentin",
            instructions=self.instructions,
            model=self.model,
            tools=[fill_crm_field, skip_crm_field]
        )
        logging.info("[LLM] Агент инициализирован")

    def get_current_stage(self):
        return self.funnel_stages[self.stage_idx]

    def get_remaining_questions(self):
        stage = self.get_current_stage()
        remaining = []
        for q in stage['questions']:
            field_id = int(q['id'])
            if field_id not in self.answered_fields:
                remaining.append(q)
        return remaining

    def _mark_field_answered(self, field_id, field_type=None, value=None):
        field_id = int(field_id)
        self.answered_fields[field_id] = {
            "type": field_type,
            "value": value
        }

    def next_stage(self):
        lead_id = get_active_lead_id()
        client = AmoCRMClient()
        next_stage_idx = self.stage_idx + 1
        if lead_id and next_stage_idx < len(STAGE_STATUS_IDS):
            status_id = STAGE_STATUS_IDS[next_stage_idx]
            status, resp = client.update_lead_status(lead_id, status_id)
            print(f"[CRM] Статус сделки обновлён: {status}, {resp}")
        if self.stage_idx < len(self.funnel_stages) - 1:
            self.stage_idx += 1
            self.answered_fields = {}
            print(f"[LLM] Переход к этапу {self.stage_idx + 1}: {self.get_current_stage()['name']}")
            return True
        return False

    def _system_info(self):
        stage = self.get_current_stage()
        remaining = self.get_remaining_questions()
        info = [
            '[Системная информация, прикрепляется автоматически]',
            f'## Текущий этап: {self.stage_idx + 1} — {stage["name"]}',
            'Данные, которые ещё не внесены в поля:'
        ]
        if remaining:
            for q in remaining:
                enums_str = ''
                if q.get('enums'):
                    enums_str = f" (варианты: {[e.get('value') for e in q['enums']]})"
                info.append(f"- id={q['id']}, name={q.get('name')}, type={q.get('type')}: {q.get('comment', '')}{enums_str}")
        else:
            info.append('- нет')
        return '\n'.join(info)

    async def process_async(self, user_text):
        if self.llm_busy:
            print("[DEBUG][STT->LLM] LLM ещё не ответила, новый запрос игнорируется.")
            return "[LLM] Пожалуйста, дождитесь ответа на предыдущий вопрос."
        async with self.lock:
            self.llm_busy = True
            try:
                print(f"[DEBUG][STT->LLM] Получен текст: {user_text}")
                print(f"[DEBUG][STT->LLM] Текущий этап: {self.stage_idx + 1} — {self.get_current_stage()['name']}")
                print(f"[DEBUG][STT->LLM] Осталось вопросов: {len(self.get_remaining_questions())}")
                while not self.get_remaining_questions():
                    print(f"[DEBUG][STT->LLM] Нет оставшихся вопросов на этапе {self.stage_idx + 1}, пробую перейти к следующему этапу...")
                    if not self.next_stage():
                        print(f"[DEBUG][STT->LLM] Воронка завершена. Все вопросы заданы.")
                        return "[Воронка завершена. Все вопросы заданы.]"
                    print(f"[DEBUG][STT->LLM] Перешли к этапу {self.stage_idx + 1}")
                    print(f"[DEBUG][STT->LLM] Осталось вопросов: {len(self.get_remaining_questions())}")
                sys_info = self._system_info()
                remaining = self.get_remaining_questions()
                if remaining:
                    names = ", ".join([q.get('name', 'Неизвестный') for q in remaining])
                    print(f"[LLM] Осталось задать вопросы: {names}")
                else:
                    print("[LLM] Все вопросы на этапе заданы или пропущены.")
                user_message = f"{user_text}\n\n<<<\n{sys_info}\n>>>"
                print(f"[DEBUG][STT->LLM] Формирую входные данные для LLM...")
                if not self.history:
                    input_data = user_message
                else:
                    input_data = self.history + [{"role": "user", "content": user_message}]
                run_config = RunConfig(tracing_disabled=False)
                try:
                    print(f"[DEBUG][STT->LLM] Запускаю LLM...")
                    result = await Runner.run(self.agent, input_data, run_config=run_config)
                    llm_reply = result.final_output
                    print(f"[DEBUG][STT->LLM] Ответ LLM получен: {llm_reply}")
                    if not self.history:
                        self.history = result.to_input_list()
                    else:
                        self.history = result.to_input_list()
                    while not self.get_remaining_questions():
                        print(f"[DEBUG][STT->LLM] После ответа LLM нет оставшихся вопросов, пробую перейти к следующему этапу...")
                        if self.next_stage():
                            sys_info = self._system_info()
                            user_message = f"\n<<<\n{sys_info}\n>>>"
                            if not self.history:
                                input_data = user_message
                            else:
                                input_data = self.history + [{"role": "user", "content": user_message}]
                            run_config = RunConfig(tracing_disabled=False)
                            print(f"[DEBUG][STT->LLM] Запускаю LLM для нового этапа...")
                            result = await Runner.run(self.agent, input_data, run_config=run_config)
                            llm_reply = result.final_output
                            print(f"[DEBUG][STT->LLM] Ответ LLM для нового этапа: {llm_reply}")
                            if not self.history:
                                self.history = result.to_input_list()
                            else:
                                self.history = result.to_input_list()
                        else:
                            print(f"[DEBUG][STT->LLM] Все этапы заполнены, завершаю работу.")
                            return "Спасибо! Все этапы заполнены, менеджер свяжется с вами для уточнения деталей."
                    return llm_reply
                except Exception as e:
                    logging.error(f"[LLM] Ошибка при обработке: {str(e)}", exc_info=True)
                    print(f"[DEBUG][STT->LLM] Произошла ошибка: {str(e)}")
                    return f"Произошла ошибка при обработке запроса: {str(e)}"
            finally:
                self.llm_busy = False

    # Для обратной совместимости (sync fallback)
    def process(self, user_text):
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if loop and loop.is_running():
            # Если уже есть event loop, запускаем асинхронно через create_task
            return asyncio.create_task(self.process_async(user_text))
        else:
            # Если нет event loop, создаём новый
            return asyncio.run(self.process_async(user_text))

# Singleton LLM-агент для всего приложения
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
    """
    Синхронная обёртка для обратной совместимости.
    """
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    if loop and loop.is_running():
        return asyncio.create_task(process_transcript_async(transcript))
    else:
        return asyncio.run(process_transcript_async(transcript))
