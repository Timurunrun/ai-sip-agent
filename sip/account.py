import threading
import queue
import pjsua2 as pj
from .call import Call
import re
from crm.status_config import STAGE_STATUS_IDS
import uuid

class Account(pj.Account):
    def __init__(self, sip_event_queue, transcript_queue=None):
        pj.Account.__init__(self)
        self.sip_event_queue = sip_event_queue
        self.transcript_queue = transcript_queue
        self.sem_reg = threading.Semaphore(0)

    def onRegState(self, prm):
        print(f"[PJSUA] Статус регистрации: {prm.reason}")
        if prm.status == 200:  # Проверяем статус регистрации
            self.sem_reg.release()

    def onIncomingCall(self, prm):
        print("[PJSUA] Входящий звонок...")
        call_id = str(uuid.uuid4())
        call = Call(self, prm.callId)
        self.sip_event_queue.current_call = call
        
        # Автоматически принимаем звонок
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 200
        call.answer(call_prm)
        print("[PJSUA] Звонок автоматически принят")

        # Получаем и выводим номер звонящего
        ci = call.getInfo()
        print(f"[PJSUA] Звонок с номера: {ci.remoteUri}")
        match = re.search(r'sip:([^@>]+)@', ci.remoteUri)
        if match:
            phone_number = match.group(1)
            print(f"[PJSUA] Номер звонящего: {phone_number}")
        else:
            print(f"[PJSUA] Не удалось извлечь номер из {ci.remoteUri}")
            phone_number = None
        # # --- Ожидание карточки и сделки в CRM ---
        # from crm.crm_api import AmoCRMClient, wait_for_contact_and_lead
        # if not phone_number:
        # print("[CRM] Нет номера для поиска контакта!")
        #     return
        # amocrm_client = AmoCRMClient()
        # contact, lead = wait_for_contact_and_lead(phone_number, amocrm_client, ringback_cb)
        # if contact and lead:
        #     print(f"[CRM] Контакт и сделка найдены: contact_id={contact['id']}, lead_id={lead['id']}")
        #     call.lead_id = lead['id']
        #     # Смена статуса на "Взята в работу"
        #     client = AmoCRMClient()
        #     status, resp = client.update_lead_status(lead['id'], STAGE_STATUS_IDS[0])
        #     print(f"[CRM] Статус сделки обновлён: {status}, {resp}")
        # else:
        #     print("[CRM] Не удалось найти контакт/сделку по номеру за отведённое время")
        #     threading.Thread(target=wait_crm, daemon=True).start()
        # # Ответ на звонок произойдет после соединения с Deepgram

# Глобальный доступ к lead_id для инструментов
_active_lead_id = None
def get_active_lead_id():
    """Возвращает ID текущей активной сделки из очереди событий"""
    import sip.call
    if sip.call.Call.current and hasattr(sip.call.Call.current.acc.sip_event_queue, 'config'):
        return sip.call.Call.current.acc.sip_event_queue.config.get('ACTIVE_LEAD_ID')