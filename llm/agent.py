from agents import Agent, Runner
import threading
from llm.config_llm import SYSTEM_PROMPT, LLM
from crm.crm_api import load_enriched_funnel_config
from llm.tools import fill_crm_field, skip_crm_field, set_remove_question_callback
from crm.status_config import STAGE_STATUS_IDS
from crm.crm_api import AmoCRMClient
from sip.utils import get_active_lead_id

class LLMAgent:
    def __init__(self, instructions=SYSTEM_PROMPT, model=LLM):
        self.instructions = instructions
        self.model = model
        self.lock = threading.Lock()
        self.history = []  # Список сообщений для контекста
        self.stage_idx = 0
        self.removed_question_ids = set()  # id вопросов, удалённых через инструмент или skip
        # Загружаем enriched funnel config из кеша
        self.funnel_stages = load_enriched_funnel_config()
        # Устанавливаем callback для инструментов
        set_remove_question_callback(self.remove_question_by_id)
        # Добавляем инструменты
        self.agent = Agent(
            name="Valentin",
            instructions=self.instructions,
            model=self.model,
            tools=[fill_crm_field, skip_crm_field]
        )

    def get_current_stage(self):
        return self.funnel_stages[self.stage_idx]

    def get_remaining_questions(self):
        stage = self.get_current_stage()
        return [q for q in stage['questions'] if q['id'] not in self.removed_question_ids]

    def remove_question_by_id(self, qid):
        self.removed_question_ids.add(qid)

    def next_stage(self):
        lead_id = get_active_lead_id()
        client = AmoCRMClient()
        # Индекс следующего этапа (текущий + 1)
        next_stage_idx = self.stage_idx + 1
        # Меняем статус, если есть lead_id и статус для следующего этапа
        if lead_id and next_stage_idx < len(STAGE_STATUS_IDS):
            status_id = STAGE_STATUS_IDS[next_stage_idx]
            status, resp = client.update_lead_status(lead_id, status_id)
            print(f"[CRM] Статус сделки обновлён: {status}, {resp}")
        if self.stage_idx < len(self.funnel_stages) - 1:
            self.stage_idx += 1
            self.removed_question_ids = set()
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

    def process(self, user_text):
        with self.lock:
            # 1. Если на этапе уже нет вопросов (например, все были пропущены инструментами), сразу перейти к следующему этапу
            while not self.get_remaining_questions():
                if not self.next_stage():
                    return "[Воронка завершена. Все вопросы заданы.]"
            # 2. Сформировать системную вставку и историю
            sys_info = self._system_info()
            remaining = self.get_remaining_questions()
            if remaining:
                names = ", ".join([q.get('name') for q in remaining])
                print(f"[LLM] Осталось задать вопросы: {names}")
            else:
                print("[LLM] Все вопросы на этапе заданы или пропущены.")
            user_message = f"{user_text}\n\n<<<\n{sys_info}\n>>>"
            if not self.history:
                input_data = user_message
            else:
                input_data = self.history + [{"role": "user", "content": user_message}]
            result = Runner.run_sync(self.agent, input_data)
            llm_reply = result.final_output
            # Обновить историю
            if not self.history:
                self.history = [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": llm_reply}
                ]
            else:
                self.history.append({"role": "user", "content": user_message})
                self.history.append({"role": "assistant", "content": llm_reply})

            # 3. Если после ответа вопросы закончились — сразу перейти к следующему этапу и сгенерировать новую реплику (бесшовно)
            while not self.get_remaining_questions():
                if self.next_stage():
                    # Системная вставка для нового этапа
                    sys_info = self._system_info()
                    # Передаём только системную вставку, чтобы LLM сразу спросила новый вопрос
                    user_message = f"\n<<<\n{sys_info}\n>>>"
                    if not self.history:
                        input_data = user_message
                    else:
                        input_data = self.history + [{"role": "user", "content": user_message}]
                    result = Runner.run_sync(self.agent, input_data)
                    llm_reply = result.final_output
                    # Обновить историю
                    if not self.history:
                        self.history = [
                            {"role": "user", "content": user_message},
                            {"role": "assistant", "content": llm_reply}
                        ]
                    else:
                        self.history.append({"role": "user", "content": user_message})
                        self.history.append({"role": "assistant", "content": llm_reply})
                else:
                    return "Спасибо! Все этапы заполнены, менеджер свяжется с вами для уточнения деталей."
            return llm_reply

# Singleton LLM-агент для всего приложения
_llm_agent_instance = None

def get_llm_agent():
    global _llm_agent_instance
    if _llm_agent_instance is None:
        _llm_agent_instance = LLMAgent()
    return _llm_agent_instance

def process_transcript(transcript):
    """
    Передаёт распознанный текст в LLM, возвращает ответ.
    Контекст диалога сохраняется между вызовами.
    """
    agent = get_llm_agent()
    return agent.process(transcript)
