import logging
from typing import Dict, Any, List
from crm.crm_api import AmoCRMClient
from crm.crm_api import load_enriched_post_funnel_config

class CRMUpdater:
    """Модуль для внесения полученных после пост-обработки звонка данных лида в CRM"""
    
    def __init__(self):
        self.client = AmoCRMClient()
        self.enriched_funnel_stages = load_enriched_post_funnel_config()
        self._build_field_mapping()
        
        logging.info("[CRM_UPDATER] Инициализирован")

    def _build_field_mapping(self) -> None:
        """Создает маппинг field_id -> field_info для быстрого поиска данных поля по его ID"""
        self.field_mapping = {}
        
        for stage in self.enriched_funnel_stages:
            for question in stage.get('questions', []):
                field_id = question.get('id')
                if field_id:
                    self.field_mapping[field_id] = {
                        'name': question.get('name', ''),
                        'type': question.get('type', ''),
                        'enums': question.get('enums', [])
                    }

    def update_lead_with_analysis(self, lead_id: str, analysis_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Заполняет поля лида в CRM на основе результатов анализа
        
        Args:
            lead_id: ID лида/сделки
            analysis_data: Результат анализа в формате {field_id: value}
            max_retries: Максимальное количество попыток
            
        Returns:
            bool: True если обновление прошло успешно
        """
        for attempt in range(1, max_retries + 1):
            try:
                logging.info(f"[CRM_UPDATER] Попытка {attempt}/{max_retries} обновления лида {lead_id}")
                
                success_count = 0
                total_fields = len(analysis_data)
                
                for field_id_str, value in analysis_data.items():
                    try:
                        field_id = int(field_id_str)
                    except (ValueError, TypeError):
                        logging.warning(f"[CRM_UPDATER] Некорректный field_id: {field_id_str}")
                        continue
                        
                    if value is None:
                        logging.debug(f"[CRM_UPDATER] Поле {field_id} пропущено (значение null)")
                        continue
                    
                    field_info = self.field_mapping.get(field_id)
                    if not field_info:
                        logging.warning(f"[CRM_UPDATER] Поле {field_id} не найдено в маппинге")
                        continue
                    
                    if self._update_single_field(lead_id, field_id, value, field_info):
                        success_count += 1
                
                if success_count > 0:
                    logging.info(f"[CRM_UPDATER] Успешно обновлено {success_count}/{total_fields} полей лида {lead_id}")
                    return True
                else:
                    logging.warning(f"[CRM_UPDATER] Ни одно поле не было обновлено для лида {lead_id}")
                    
            except Exception as e:
                logging.error(f"[CRM_UPDATER] Ошибка на попытке {attempt}: {e}")
                
                if attempt < max_retries:
                    logging.info(f"[CRM_UPDATER] Повторная попытка через 1 секунду...")
                    import time
                    time.sleep(1)
                else:
                    logging.error(f"[CRM_UPDATER] Исчерпаны все попытки для лида {lead_id}")
                    return False
        
        return False

    def _update_single_field(self, lead_id: str, field_id: int, value: Any, field_info: Dict[str, Any]) -> bool:
        """
        Заполняет одно поле в карточке лида
        
        Args:
            lead_id: ID лида/сделки
            field_id: ID поля
            value: Значение для записи
            field_info: Информация о поле (type, enums)
            
        Returns:
            bool: True, если обновление прошло успешно
        """
        try:
            field_type = field_info.get('type', 'text')
            field_name = field_info.get('name', f'Field_{field_id}')
            
            # Обработка enum-полей
            enum_id = None
            if field_type in ['select', 'multiselect'] and field_info.get('enums'):
                enum_id = self._resolve_enum_value(value, field_info.get('enums', []), field_type)
            
            status_code, response_text = self.client.update_lead_field(
                lead_id=int(lead_id),
                field_id=field_id,
                value=value,
                field_type=field_type,
                enum_id=enum_id
            )
            
            if status_code == 200:
                logging.debug(f"[CRM_UPDATER] Поле '{field_name}' (ID: {field_id}) обновлено успешно")
                return True
            else:
                logging.error(f"[CRM_UPDATER] Ошибка обновления поля '{field_name}' (ID: {field_id}): {status_code} - {response_text}")
                return False
                
        except Exception as e:
            logging.error(f"[CRM_UPDATER] Исключение при обновлении поля {field_id}: {e}")
            return False

    def _resolve_enum_value(self, value: Any, enums: List[Dict], field_type: str) -> Any:
        """
        Преобразует значение для enum-полей

        Args:
            value: Значение из анализа
            enums: Список enum-вариантов
            field_type: Тип поля (select/multiselect)
            
        Returns:
            enum_id или список enum_id для multiselect
        """
        if field_type == 'multiselect' and isinstance(value, list):
            # Для multiselect возвращаем список ID
            return [int(v) for v in value if self._is_valid_enum_id(v, enums)]
        elif field_type == 'select':
            # Для select возвращаем один ID
            if self._is_valid_enum_id(value, enums):
                return int(value)
        
        return None

    def _is_valid_enum_id(self, enum_id: Any, enums: List[Dict]) -> bool:
        """Проверяет, существует ли enum_id в списке вариантов"""
        try:
            enum_id_int = int(enum_id)
            return any(enum.get('id') == enum_id_int for enum in enums)
        except (ValueError, TypeError):
            return False


# Глобальный экземпляр updater'а
_crm_updater_instance = None

def get_crm_updater() -> CRMUpdater:
    """Получает глобальный экземпляр CRM updater'а"""
    global _crm_updater_instance
    if _crm_updater_instance is None:
        _crm_updater_instance = CRMUpdater()
    return _crm_updater_instance
