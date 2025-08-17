import logging
import json
import os
from typing import Dict, Any, List
from crm.crm_api import AmoCRMClient
from crm.crm_api import load_enriched_post_funnel_config

class CRMUpdater:
    """Модуль для внесения полученных после пост-обработки звонка данных лида в CRM"""
    
    def __init__(self):
        self.client = AmoCRMClient()
        self.enriched_funnel_stages = load_enriched_post_funnel_config()
        self._build_field_mapping()
        self._load_stages()
        
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

    def _load_stages(self) -> None:
        """Загружает список статусов из stages.json"""
        try:
            stages_file = os.path.join(os.path.dirname(__file__), '..', '..', 'crm', 'funnel', 'stages.json')
            with open(stages_file, 'r', encoding='utf-8') as f:
                self.stages = json.load(f)
            
            if self.stages:
                self.final_stage_id = self.stages[-1]  # Последний статус из списка
                logging.info(f"[CRM_UPDATER] Загружено {len(self.stages)} статусов, финальный статус: {self.final_stage_id}")
            else:
                self.final_stage_id = None
                logging.warning("[CRM_UPDATER] Список статусов пуст")
        except Exception as e:
            logging.error(f"[CRM_UPDATER] Ошибка загрузки статусов: {e}")
            self.stages = []
            self.final_stage_id = None

    def update_lead_with_analysis(self, lead_id: str, analysis_data: Dict[str, Any]) -> bool:
        """
        Заполняет поля лида в CRM на основе результатов анализа
        
        Args:
            lead_id: ID лида/сделки
            analysis_data: Результат анализа в формате {field_id: value}
              
        Returns:
            bool: True если обновление прошло успешно
        """
        try:
            logging.info(f"[CRM_UPDATER] Обновление лида {lead_id}")
            
            success_count = 0
            failed_fields = []
            processed_fields = 0
            
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
                
                processed_fields += 1
                field_name = field_info.get('name', f'Field_{field_id}')
                
                if self._update_single_field(lead_id, field_id, value, field_info):
                    success_count += 1
                else:
                    failed_fields.append(f"{field_name} (ID: {field_id})")
            
            if processed_fields == 0:
                logging.warning(f"[CRM_UPDATER] Нет полей для обновления лида {lead_id}")
                # Если нет полей для обновления, добавляем приписку в лог-файл и считаем операцию успешной
                try:
                    self._append_note_to_latest_analysis_file(
                        lead_id=str(lead_id),
                        note="Нет полей для обновления (все значения null)."
                    )
                except Exception as e:
                    logging.error(f"[CRM_UPDATER] Не удалось записать приписку о пустом обновлении полей CRM в файл анализа для лида {lead_id}: {e}")
                return True
            
            if success_count == processed_fields:
                logging.info(f"[CRM_UPDATER] Успешно обновлены ВСЕ поля ({success_count}/{processed_fields}) лида {lead_id}")
                
                # Изменяем статус лида на финальный этап после успешного заполнения всех полей
                if self.final_stage_id:
                    self._update_lead_status(lead_id, self.final_stage_id)
                
                return True
            else:
                logging.warning(f"[CRM_UPDATER] Обновлено только {success_count}/{processed_fields} полей лида {lead_id}")
                if failed_fields:
                    logging.warning(f"[CRM_UPDATER] Поля с ошибками: {', '.join(failed_fields)}")
                return False
                
        except Exception as e:
            logging.error(f"[CRM_UPDATER] Ошибка при обновлении лида {lead_id}: {e}")
            return False

    def _append_note_to_latest_analysis_file(self, lead_id: str, note: str) -> None:
        """
        Находит последний файл анализа для лида и добавляет к нему приписку о результате обновления CRM.

        Формат файлов: post_analysis_lead_{lead_id}_{timestamp}_attempt_{attempt}.json
        Файлы создаются модулем PostCallProcessor в папке tmp рядом с этим модулем.
        """
        try:
            tmp_dir = os.path.join(os.path.dirname(__file__), '..', 'tmp')
            if not os.path.isdir(tmp_dir):
                logging.debug(f"[CRM_UPDATER] Папка tmp не найдена: {tmp_dir}")
                return

            prefix = f"post_analysis_lead_{lead_id}_"
            candidates = [
                f for f in os.listdir(tmp_dir)
                if f.startswith(prefix) and f.endswith('.json')
            ]

            if not candidates:
                logging.debug(f"[CRM_UPDATER] Файлы анализа для лида {lead_id} не найдены в {tmp_dir}")
                return

            # Берем самый новый по времени модификации
            latest = max(
                candidates,
                key=lambda name: os.path.getmtime(os.path.join(tmp_dir, name))
            )
            latest_path = os.path.join(tmp_dir, latest)

            with open(latest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Добавляем приписку (на верхнем уровне под ключом crm_update_note)
            # Если ранее была приписка, преобразуем в список заметок
            existing_note = data.get('crm_update_note')
            if existing_note is None:
                data['crm_update_note'] = note
            else:
                # Храним как список
                if isinstance(existing_note, list):
                    existing_note.append(note)
                    data['crm_update_note'] = existing_note
                else:
                    data['crm_update_note'] = [existing_note, note]

            with open(latest_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"[CRM_UPDATER] Приписка добавлена в файл анализа: {os.path.basename(latest_path)}")

        except Exception as e:
            # Не прерываем основной поток выполнения из-за проблем с лог-файлом
            logging.error(f"[CRM_UPDATER] Ошибка добавления приписки в файл анализа лида {lead_id}: {e}")

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
            valid_ids = [int(v) for v in value if self._is_valid_enum_id(v, enums)]
            return valid_ids if valid_ids else None
        elif field_type == 'select':
            # Для select возвращаем один ID
            if isinstance(value, list):
                # Если для select-поля передан массив, берем первый валидный элемент
                logging.warning(f"[CRM_UPDATER] Для select-поля передан массив {value}, используем первый валидный элемент")
                for v in value:
                    if self._is_valid_enum_id(v, enums):
                        return int(v)
                return None
            else:
                # Обычная обработка одиночного значения
                if self._is_valid_enum_id(value, enums):
                    return int(value)
        
        return None

    def _update_lead_status(self, lead_id: str, status_id: int) -> bool:
        """
        Обновляет статус лида в CRM
        
        Args:
            lead_id: ID лида/сделки
            status_id: ID нового статуса
            
        Returns:
            bool: True если обновление прошло успешно
        """
        try:
            status_code, response_text = self.client.update_lead_status(
                lead_id=int(lead_id),
                status_id=status_id
            )
            
            if status_code == 200:
                logging.info(f"[CRM_UPDATER] Статус лида {lead_id} успешно обновлен на {status_id}")
                return True
            else:
                logging.error(f"[CRM_UPDATER] ОШИБКА обновления статуса лида {lead_id}: {status_code} - {response_text}")
                return False
                
        except Exception as e:
            logging.error(f"[CRM_UPDATER] ОШИБКА при обновлении статуса лида {lead_id}: {e}")
            return False

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
