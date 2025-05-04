import os
import requests
import logging
import time
from typing import Optional, Any
from dotenv import load_dotenv
load_dotenv()

class AmoCRMClient:
    """
    Удобный клиент для работы с AmoCRM API через постоянный access_token.
    """
    def __init__(self, subdomain: Optional[str] = None, access_token: Optional[str] = None):
        self.subdomain = subdomain or os.getenv("AMOCRM_SUBDOMAIN")
        self.access_token = access_token or os.getenv("AMOCRM_ACCESS_TOKEN")
        if not self.subdomain or not self.access_token:
            raise ValueError("Необходимо указать subdomain и access_token либо через параметры, либо через переменные окружения")

    def _base_request(self, endpoint: str, req_type: str = "get", parameters: Optional[dict] = None, data: Optional[dict] = None):
        url = f"https://{self.subdomain}.amocrm.ru{endpoint}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            if req_type == "get":
                response = requests.get(url, headers=headers)
            elif req_type == "get_param":
                response = requests.get(url, headers=headers, params=parameters)
            elif req_type == "post":
                response = requests.post(url, headers=headers, json=data)
            elif req_type == "patch":
                response = requests.patch(url, headers=headers, json=data)
            else:
                raise ValueError(f"Неизвестный тип запроса: {req_type}")
            response.raise_for_status()
            try:
                return response.json()
            except Exception as e:
                logging.error(f"Не удалось декодировать JSON. HTTP status: {response.status_code}, Response text: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logging.exception(f"Ошибка запроса к AmoCRM: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"HTTP status: {e.response.status_code}, Response text: {e.response.text}")
            return None
        except Exception as e:
            logging.exception(f"Ошибка обработки ответа AmoCRM: {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                logging.error(f"Raw response text: {response.text}")
            return None

    def find_contact_by_phone(self, phone: str, limit: int = 10, with_params: str = None):
        endpoint = "/api/v4/contacts"
        params = {"query": phone, "limit": limit}
        if with_params:
            params["with"] = with_params
        return self._base_request(endpoint=endpoint, req_type="get_param", parameters=params)

    def get_lead_by_id(self, lead_id: int, with_params: str = None):
        endpoint = f"/api/v4/leads/{lead_id}"
        params = {}
        if with_params:
            params["with"] = with_params
        return self._base_request(endpoint=endpoint, req_type="get_param", parameters=params)

    def get_lead_custom_fields(self):
        endpoint = "/api/v4/leads/custom_fields"
        return self._base_request(endpoint=endpoint, req_type="get")

    def get_lead_custom_field_by_id(self, field_id: int):
        endpoint = f"/api/v4/leads/custom_fields/{field_id}"
        return self._base_request(endpoint=endpoint, req_type="get")
    
    def update_lead_status(self, lead_id: int, status_id: int):
        endpoint = f"/api/v4/leads/{lead_id}"
        headers = self._get_headers()
        data = {"status_id": status_id}
        url = f"https://{self.subdomain}.amocrm.ru{endpoint}"
        resp = requests.patch(url, headers=headers, json=data)
        return resp.status_code, resp.text

    def update_lead_field(self, lead_id: int, field_id: int, value, field_type: str, enum_id: int = None):
        endpoint = f"/api/v4/leads/{lead_id}"
        headers = self._get_headers()
        data = {"custom_fields_values": []}
        field_obj = {"field_id": field_id, "values": []}
        # Явная обработка ключевых типов
        if field_type == "text":
            field_obj["values"].append({"value": str(value)})
        elif field_type == "textarea":
            field_obj["values"].append({"value": str(value)})
        elif field_type == "numeric":
            field_obj["values"].append({"value": float(value)})
        elif field_type == "checkbox":
            field_obj["values"].append({"value": bool(value)})
        elif field_type == "select":
            if enum_id:
                field_obj["values"].append({"enum_id": enum_id})
            else:
                field_obj["values"].append({"value": value})
        elif field_type == "multiselect":
            # value — список enum_id или value
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, int):
                        field_obj["values"].append({"enum_id": v})
                    else:
                        field_obj["values"].append({"value": v})
            elif enum_id:
                field_obj["values"].append({"enum_id": enum_id})
            else:
                field_obj["values"].append({"value": value})
        elif field_type == "date":
            field_obj["values"].append({"value": value})  # value = unix timestamp (int) или RFC-3339 string
        else:
            field_obj["values"].append({"value": value})
        data["custom_fields_values"].append(field_obj)
        url = f"https://{os.environ.get('AMOCRM_SUBDOMAIN')}.amocrm.ru{endpoint}"
        resp = requests.patch(url, headers=headers, json=data)
        return resp.status_code, resp.text

    def _get_headers(self):
        access_token = os.environ.get("AMOCRM_ACCESS_TOKEN")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "amoCRM-API-client/1.0"
        }
        return headers

def wait_for_contact_and_lead(phone_number: str, amocrm_client: AmoCRMClient, ringback_callback, max_wait: float = 10.0, poll_interval: float = 0.7):
    start = time.time()
    contact = None
    lead = None
    played_ringback = False
    while time.time() - start < max_wait:
        contacts = amocrm_client.find_contact_by_phone(phone_number, with_params="leads")
        if contacts and contacts.get('_embedded', {}).get('contacts'):
            contact = contacts['_embedded']['contacts'][0]
            leads = contact.get('_embedded', {}).get('leads', [])
            if leads:
                lead_id = leads[0]['id']
                lead = amocrm_client.get_lead_by_id(lead_id)
                break
        if not played_ringback:
            ringback_callback(start=True)
            played_ringback = True
        time.sleep(poll_interval)
    ringback_callback(start=False)
    return contact, lead

# --- ENRICH FUNNEL CONFIG WITH CRM FIELDS ---
import json
from llm.funnel_config import FUNNEL_STAGES
ENRICHED_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'enriched_funnel_config.json')

def load_enriched_funnel_config():
    """
    Загружает enriched funnel config из enriched_funnel_config.json
    """
    try:
        with open(ENRICHED_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Не удалось загрузить enriched funnel config из файла: {e}")

def enrich_funnel_config_with_crm():
    """
    Возвращает enriched funnel config: список этапов, где каждый вопрос содержит id, comment, name, type, enums (если есть).
    Также сохраняет результат в enriched_funnel_config.json (перезаписывает при каждом запуске).
    """
    client = AmoCRMClient()
    print('[CRM_SYNC] Получаем поля AmoCRM через API...')
    crm_fields = client.get_lead_custom_fields()
    if not crm_fields or '_embedded' not in crm_fields or 'custom_fields' not in crm_fields['_embedded']:
        raise RuntimeError("Не удалось получить список полей AmoCRM!")
    crm_fields_map = {}
    for f in crm_fields['_embedded']['custom_fields']:
        crm_fields_map[f['id']] = {
            'name': f.get('name'),
            'type': f.get('type'),
            'enums': f.get('enums') if 'enums' in f else None
        }
    enriched_stages = []
    total_questions = 0
    enriched_questions_count = 0
    skipped_questions_count = 0
    for stage in FUNNEL_STAGES:
        enriched_questions = []
        for q in stage['questions']:
            qid = q.get('id')
            if not qid:
                continue  # skip вопросы без id
            total_questions += 1
            crm_data = crm_fields_map.get(qid)
            if not crm_data:
                skipped_questions_count += 1
                logging.warning(f"Вопрос с id={qid} не найден в AmoCRM, пропущен!")
                continue
            enums_sorted = None
            if crm_data['enums']:
                enums_sorted = sorted(crm_data['enums'], key=lambda x: x.get('sort', 0))
            enriched_q = {
                'id': qid,
                'comment': q.get('comment', ''),
                'name': crm_data['name'],
                'type': crm_data['type'],
                'enums': enums_sorted
            }
            enriched_questions.append(enriched_q)
            enriched_questions_count += 1
        enriched_stages.append({
            'name': stage['name'],
            'questions': enriched_questions
        })
    print(f"[CRM_SYNC] Сводка: этапов={len(enriched_stages)}, вопросов всего={total_questions}, успешно обогащено={enriched_questions_count}, пропущено={skipped_questions_count}")
    # Сохраняем в файл
    with open(ENRICHED_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(enriched_stages, f, ensure_ascii=False, indent=2)
    print(f"[CRM_SYNC] Enriched funnel config сохранён в {os.path.abspath(ENRICHED_CONFIG_PATH)}")
    return enriched_stages
