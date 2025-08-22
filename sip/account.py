import threading
import pjsua2 as pj
from .call import Call
import re
import json
import uuid
import os
import time
from pathlib import Path

# Создаем папку для временных файлов записей
TMP_RECORDINGS_DIR = Path("/tmp/pjsua_recordings")
TMP_RECORDINGS_DIR.mkdir(exist_ok=True)

def load_stage_status_ids():
    """Загружает статусы этапов воронки"""
    try:
        stages_file = os.path.join(os.path.dirname(__file__), '..', 'crm', 'funnel', 'stages.json')
        with open(stages_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[CRM] Ошибка при загрузке stages.json: {e}")

class Account(pj.Account):
    def __init__(self, sip_event_queue, transcript_queue=None):
        pj.Account.__init__(self)
        self.sip_event_queue = sip_event_queue
        self.transcript_queue = transcript_queue
        self.sem_reg = threading.Semaphore(0)

    def onRegState(self, prm):
        print(f"[PJSUA] Статус регистрации: {prm.reason}")
        if prm.reason == 'Ok':
            self.sem_reg.release()

    def onIncomingCall(self, prm):
        print("[PJSUA] Входящий звонок...")
        call = Call(self, prm.callId)
        self.sip_event_queue.current_call = call

        # Инициализируем LLM-агент
        from llm.live_call import get_llm_agent
        get_llm_agent()

        ci = call.getInfo()
        print(f"[PJSUA] Звонок с номера: {ci.remoteUri}")

        # Фильтр SIPVicious
        if "sipvicious" in ci.remoteUri.lower():
            print("[PJSUA] Обнаружен звонок от sipvicious, отклоняем...")
            try:
                call_prm = pj.CallOpParam()
                call_prm.statusCode = 403
                call.answer(call_prm)
                call.hangup()
            except Exception as e:
                print(f"[PJSUA] Ошибка при отклонении: {e}")
            return

        match = re.search(r'sip:([^@>]+)@', ci.remoteUri)
        phone_number = match.group(1) if match else None
        if not phone_number:
            print(f"[PJSUA] Не удалось извлечь номер из {ci.remoteUri}")
            return
        print(f"[PJSUA] Номер звонящего: {phone_number}")

        # 1. Поиск контакта/сделки в CRM
        from crm.crm_api import AmoCRMClient, wait_for_contact_and_lead
        amocrm_client = AmoCRMClient()
        max_attempts = 5
        lead_found = False
        for attempt in range(1, max_attempts + 1):
            contact, lead = wait_for_contact_and_lead(phone_number, amocrm_client, ringback_callback=lambda **kwargs: None)
            if lead and 'id' in lead:
                call.lead_id = lead['id']
                if hasattr(self.sip_event_queue, 'config') and isinstance(self.sip_event_queue.config, dict):
                    self.sip_event_queue.config['ACTIVE_LEAD_ID'] = lead['id']
                print(f"[CRM] Контакт/сделка: contact_id={contact.get('id') if contact else None}, lead_id={lead['id']}")
                lead_found = True
                break
            print(f"[CRM] Попытка {attempt}: контакт/сделка не найдены")
            if attempt < max_attempts:
                time.sleep(1.0)

        if not lead_found:
            print("[CRM] Сделка не найдена, сбрасываем вызов")
            try:
                call.hangup()
            except Exception as e:
                print(f"[CRM] Ошибка при сбросе: {e}")
            return

        # 2. Принять вызов и подключить STT запись
        timestamp = int(time.time())
        filename = TMP_RECORDINGS_DIR / f"call_{timestamp}.wav"
        call.connect_stt_session(str(filename))

        call_prm = pj.CallOpParam()
        call_prm.statusCode = 200
        call.answer(call_prm)
        print("[PJSUA] Вызов принят")

        # 3. Обновить статус сделки
        if hasattr(call, 'lead_id'):
            try:
                stage_status_ids = load_stage_status_ids()
                status, resp = amocrm_client.update_lead_status(call.lead_id, stage_status_ids[0])
                print(f"[CRM] Статус сделки обновлён: {status}, {resp}")
            except Exception as e:
                print(f"[CRM] Ошибка обновления статуса: {e}")

        def start_streaming_after_answer():
            while not hasattr(call, '_audio_media') or call._audio_media is None:
                time.sleep(0.05)
            call.start_audio_streaming(0)
        threading.Thread(target=start_streaming_after_answer, daemon=True).start()

_active_lead_id = None