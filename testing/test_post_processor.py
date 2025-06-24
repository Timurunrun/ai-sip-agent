"""
Тест постобработки звонка
"""

import sys
import os
import asyncio
import json

# Добавляем родительскую папку в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.post_processing.post_processor import PostCallProcessor

def load_test_dialogs():
    """Загружает тестовые диалоги из файла"""
    dialogs_path = os.path.join(os.path.dirname(__file__), 'test_dialogs.json')
    with open(dialogs_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def select_dialog():
    """Отображает меню для выбора диалога"""
    dialogs = load_test_dialogs()
    
    print("\nДоступные тестовые диалоги:")
    print("=" * 50)
    
    dialog_keys = list(dialogs.keys())
    for i, key in enumerate(dialog_keys, 1):
        description = dialogs[key].get('description', 'Без описания')
        print(f"{i}. {key}")
        print(f"   {description}")
        print()
    
    while True:
        try:
            choice = input(f"Выберите диалог (1-{len(dialog_keys)}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(dialog_keys):
                selected_key = dialog_keys[choice_num - 1]
                return selected_key, dialogs[selected_key]['dialog']
            else:
                print("Неверный номер. Попробуйте снова.")
        except (ValueError, KeyboardInterrupt):
            print("\nОтмена.")
            return None, None


async def test_post_processor():
    """
    Основная функция тестирования постобработки
    """
    print("ТЕСТИРОВАНИЕ ПОСТОБРАБОТКИ ЗВОНКА")
    
    dialog_key, test_history = select_dialog()
    if not test_history:
        print("Тест отменен.")
        return
    
    test_lead_id = f"test_{dialog_key}_{20250624}_140000"
    
    print(f"\n1. Выбран диалог: {dialog_key}")
    print(f"   - ID лида: {test_lead_id}")
    print(f"   - Количество сообщений: {len(test_history)}")
    
    print(f"\n2. История диалога:")
    print("-" * 50)
    for msg in test_history:
        role = "МЕНЕДЖЕР" if msg["role"] == "assistant" else "КЛИЕНТ"
        print(f"{role}: {msg['content']}")
    print("-" * 50)
    
    print(f"\n3. Инициализация постпроцессора...")
    processor = PostCallProcessor()
    
    print(f"\n4. Запуск постобработки...")
    await processor._process_call_history(test_lead_id, test_history)
    
    print(f"\n5. Постобработка завершена!")
    print(f"   Результат должен быть сохранен в папке tmp/")

def main():
    """
    Точка входа в программу
    """
    try:
        asyncio.run(test_post_processor())
        
    except KeyboardInterrupt:
        print("\nТест прерван пользователем")
    except Exception as e:
        print(f"\nОШИБКА при выполнении теста: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()