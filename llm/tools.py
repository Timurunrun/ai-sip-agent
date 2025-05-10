from agents import function_tool
from typing import Any
from crm.crm_api import AmoCRMClient

# Хранение референса на callback-функцию
remove_question_callback = None

def set_remove_question_callback(cb):
    """Устанавливает callback-функцию для отметки вопроса как отвеченного"""
    global remove_question_callback
    remove_question_callback = cb

@function_tool
def fill_crm_field(field_id: int, field_type: str, value: str):
    """
    Заполнить одно поле в CRM-системе (через API AmoCRM).
    Args:
        field_id: ID поля
        field_type: Тип поля (text, textarea, numeric, checkbox, select, multiselect, date)
        value: Значение для поля (всегда строка; преобразуется внутри функции по field_type)
    """
    print(f'[TOOL] Заполнить поле: id={field_id}, type={field_type}, value={value}')
    # Получаем lead_id из текущего активного звонка (Call)
    from sip.utils import get_active_lead_id
    lead_id = get_active_lead_id()
    if not lead_id:
        print('[TOOL][CRM] Нет активной сделки для внесения данных!')
        return None
    
    # Преобразование value по типу поля
    enum_id = None
    if field_type in ("select", "multiselect"):
        # value может быть строкой с запятыми или списком значений (enum values)
        values = [v.strip() for v in value.split(",") if v.strip()]
        # Получаем список вариантов поля (enums) из AmoCRM
        client = AmoCRMClient()
        field_info = client.get_lead_custom_field_by_id(field_id)
        enums = field_info.get('enums')
        if enums:
            # Для select ищем первый совпавший enum_id
            if field_type == "select":
                for enum in enums:
                    if enum['value'] == values[0]:
                        enum_id = enum['id']
                        break
                value_to_send = None
            else:  # multiselect
                enum_ids = []
                for v in values:
                    for enum in enums:
                        if enum['value'] == v:
                            enum_ids.append(enum['id'])
                            break
                value_to_send = enum_ids
        else:
            value_to_send = values
    elif field_type == "numeric":
        try:
            value_to_send = float(value) if "." in value else int(value)
        except Exception:
            value_to_send = value
    elif field_type == "checkbox":
        value_to_send = value.lower() in ("true", "1", "yes", "on", "да")
    else:
        value_to_send = value
    
    client = AmoCRMClient()
    status, resp = client.update_lead_field(lead_id, field_id, value_to_send, field_type, enum_id)
    print(f"[TOOL][CRM] PATCH status={status}, response={resp}")
    
    # Отмечаем вопрос как отвеченный
    if remove_question_callback:
        remove_question_callback(field_id, field_type, value)
    
    if status == 200:
        result_msg = "Поле успешно заполнено"
    else:
        result_msg = f"Не удалось заполнить поле: {resp}"
    return result_msg

@function_tool
def skip_crm_field(field_id: int):
    """
    Оставить пустым одно поле в CRM-системе.
    Args:
        field_id: ID поля
    """
    print(f'[TOOL] Скипнуть поле: id={field_id}')
    
    # Отмечаем вопрос как пропущенный
    if remove_question_callback:
        remove_question_callback(field_id, "skipped", "ПРОПУЩЕНО")
    
    return "Поле пропущено"
