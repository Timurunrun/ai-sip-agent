import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

from groq import Groq
from crm.crm_api import load_enriched_post_funnel_config


class PostCallProcessor:
    """Обработчик для анализа истории звонков после их завершения"""
    
    def __init__(self):
        self.client = Groq()
        self.model = "qwen-qwq-32b"
        self.tmp_dir = os.path.join(os.path.dirname(__file__), '..', 'tmp')
        os.makedirs(self.tmp_dir, exist_ok=True)
        
        # Загружаем обогащенную конфигурацию постобработки
        self.enriched_funnel_stages = load_enriched_post_funnel_config()
        
        logging.info(f"[POST_PROCESSOR] Инициализирован с моделью {self.model}")

    def _create_system_prompt(self) -> str:
        """Создает системный промпт для анализа истории звонка"""
        
        # Формируем JSON схему с типами данных из CRM
        schema_fields = []
        for stage in self.enriched_funnel_stages:
            for question in stage.get('questions', []):
                question_id = question.get('id')
                question_name = question.get('name', f'Вопрос {question_id}')
                question_type = question.get('type', 'text')
                comment = question.get('comment', '')
                enums = question.get('enums', [])
                
                # Определяем тип данных для JSON схемы
                json_type = self._map_crm_type_to_json_type(question_type, enums)
                
                # Добавляем информацию о вариантах ответов если есть
                enum_info = ""
                if enums:
                    # Создаем список вариантов с ID и значениями для понимания модели
                    enum_mappings = []
                    for enum in enums:
                        enum_id = enum.get('id')
                        enum_value = enum.get('value', '')
                        if enum_id and enum_value:
                            enum_mappings.append(f'{enum_id}="{enum_value}"')
                    
                    if enum_mappings:
                        enum_info = f' // Варианты (возвращай только ID): {", ".join(enum_mappings)}'
                
                comment_info = f' // {comment}' if comment else ''
                
                schema_field = f'"{question_id}": {json_type}{enum_info}{comment_info}'
                schema_fields.append(schema_field)
        
        schema_text = ',\n  '.join(schema_fields)
        
        system_prompt = f"""Ты - аналитик истории звонков. Проанализируй диалог между менеджером и клиентом и извлеки ответы на все указанные вопросы.

Верни результат ТОЛЬКО в формате JSON со следующей структурой:
{{
  {schema_text}
}}

Правила анализа:
- Если на вопрос есть четкий ответ в диалоге - запиши его
- Если ответа нет - null
- Для полей с вариантами ответов возвращай ТОЛЬКО ID варианта (число), НЕ текстовое значение
- Для множественного выбора (multiselect) возвращай массив ID: [123, 456]
- Для одиночного выбора (select) возвращай один ID: 123
- Соблюдай типы данных: строки в кавычках, числа и ID без кавычек, булевы как true/false
- Отвечай кратко и по существу
- НЕ придумывай данные, которых нет в диалоге

Ответ должен содержать ТОЛЬКО JSON объект без дополнительных комментариев."""

        return system_prompt

    def _map_crm_type_to_json_type(self, crm_type: str, enums: List[Dict] = None) -> str:
        """Преобразует тип поля CRM в тип JSON схемы"""
        # Если есть варианты ответов, возвращаем ID как число
        if enums and len(enums) > 0:
            if crm_type == 'multiselect':
                return '[number]'  # Массив ID для множественного выбора
            else:
                return 'number'    # Одиночный ID для обычного выбора
        
        # Стандартные типы без вариантов
        type_mapping = {
            'text': '"string"',
            'textarea': '"string"', 
            'numeric': 'number',
            'checkbox': 'boolean',
            'select': '"string"',
            'multiselect': '["string"]',
            'date': '"string"',
            'datetime': '"string"',
            'url': '"string"',
            'phone': '"string"',
            'email': '"string"'
        }
        return type_mapping.get(crm_type, '"string"')

    def process_call_history_async(self, lead_id: str, history: List[Dict[str, Any]]) -> None:
        """
        Асинхронно обрабатывает историю звонка в отдельном потоке
        
        Args:
            lead_id: ID лида/сделки
            history: История диалога
        """
        def run_processing():
            try:
                asyncio.run(self._process_call_history(lead_id, history))
            except Exception as e:
                logging.error(f"[POST_PROCESSOR] Ошибка в асинхронной обработке: {e}")
        
        # Запускаем в отдельном потоке, чтобы не блокировать основной поток
        thread = threading.Thread(target=run_processing, daemon=True)
        thread.start()
        logging.info(f"[POST_PROCESSOR] Запущена постобработка для лида {lead_id}")

    async def _process_call_history(self, lead_id: str, history: List[Dict[str, Any]]) -> None:
        """
        Основная логика обработки истории звонка
        
        Args:
            lead_id: ID лида/сделки  
            history: История диалога
        """
        try:
            # Формируем текст диалога для анализа
            dialog_text = self._format_dialog_for_analysis(history)
            
            if not dialog_text.strip():
                logging.warning(f"[POST_PROCESSOR] Пустая история для лида {lead_id}")
                return
            
            # Создаем промпт для анализа
            system_prompt = self._create_system_prompt()
            
            # Отправляем запрос к Groq
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Проанализируй этот диалог:\n\n{dialog_text}"}
            ]
            
            logging.info(f"[POST_PROCESSOR] Отправляем запрос к Groq для лида {lead_id}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            
            analysis_result = response.choices[0].message.content
            
            # Сохраняем результат в tmp
            self._save_analysis_result(lead_id, analysis_result, dialog_text)
            
            logging.info(f"[POST_PROCESSOR] Анализ завершен для лида {lead_id}")
            
        except Exception as e:
            logging.error(f"[POST_PROCESSOR] Ошибка обработки истории для лида {lead_id}: {e}")

    def _format_dialog_for_analysis(self, history: List[Dict[str, Any]]) -> str:
        """Форматирует историю диалога для анализа"""
        dialog_lines = []
        
        for msg in history:
            role = msg.get('role', '').lower()
            content = str(msg.get('content', '')).strip()
            
            if not content:
                continue
                
            if role == 'user':
                dialog_lines.append(f"КЛИЕНТ: {content}")
            elif role == 'assistant':
                dialog_lines.append(f"МЕНЕДЖЕР: {content}")
        
        return '\n'.join(dialog_lines)

    def _save_analysis_result(self, lead_id: str, analysis_json: str, original_dialog: str) -> None:
        """Сохраняет результат анализа в файл"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"post_analysis_lead_{lead_id}_{timestamp}.json"
        filepath = os.path.join(self.tmp_dir, filename)
        
        try:
            # Проверяем, что результат - валидный JSON
            parsed_result = json.loads(analysis_json)
            
            # Создаем полный результат с метаданными
            full_result = {
                "lead_id": lead_id,
                "timestamp": timestamp,
                "analysis": parsed_result,
                "original_dialog": original_dialog,
                "model_used": self.model
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(full_result, f, ensure_ascii=False, indent=2)
            
            logging.info(f"[POST_PROCESSOR] Результат сохранен: {filename}")
            
        except json.JSONDecodeError as e:
            logging.error(f"[POST_PROCESSOR] Неверный JSON от модели: {e}")
            # Сохраняем как есть для отладки
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(analysis_json)
        except Exception as e:
            logging.error(f"[POST_PROCESSOR] Ошибка сохранения результата: {e}")


# Глобальный экземпляр процессора
_post_processor_instance = None

def get_post_processor() -> PostCallProcessor:
    """Получает глобальный экземпляр постпроцессора"""
    global _post_processor_instance
    if _post_processor_instance is None:
        _post_processor_instance = PostCallProcessor()
    return _post_processor_instance

def process_call_end(lead_id: str, history: List[Dict[str, Any]]) -> None:
    """
    Запускает постобработку завершенного звонка
    
    Args:
        lead_id: ID лида/сделки
        history: История диалога
    """
    processor = get_post_processor()
    processor.process_call_history_async(lead_id, history)
