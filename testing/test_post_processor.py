"""
Тест постобработки звонка
"""

import sys
import os
import asyncio
import logging

# Добавляем родительскую папку в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.post_call_processor import PostCallProcessor

def create_test_dialog_history():
    """
    Создает тестовую историю диалога
    """
    
    history = [
        {
            "role": "assistant", 
            "content": "Добрый день, меня зовут Валентин. Вы звоните по питанию?"
        },
        {
            "role": "user", 
            "content": "Алло, да, здравствуйте. У нас стройка, нужно кормить рабочих."
        },
        {
            "role": "assistant", 
            "content": "Сколько человек у вас будет?"
        },
        {
            "role": "user", 
            "content": "Ну смотрите, у нас бригада основная человек сорок пять, но еще подрядчики приезжают, итого может быть человек семьдесят максимум."
        },
        {
            "role": "assistant", 
            "content": "Семьдесят человек максимум, понял. На какой период?"
        },
        {
            "role": "user", 
            "content": "Объект долгосрочный, строим до конца года точно, может и больше года потянется."
        },
        {
            "role": "assistant", 
            "content": "Какой адрес доставки?"
        },
        {
            "role": "user", 
            "content": "Слушайте, мне сейчас звонят по работе, отправьте на ватсап плиз. Только не на этот номер, у меня рабочий телефон. На восемь девять два три четыре пять шесть семь восемь девять ноль отправьте, это мой личный."
        }
    ]
    
    return history


async def test_post_processor():
    """
    Основная функция тестирования постобработки
    """
    print("ТЕСТИРОВАНИЕ ПОСТОБРАБОТКИ ЗВОНКА")
    
    # Создаем тестовую историю диалога
    test_history = create_test_dialog_history()
    test_lead_id = "test_complex_lead_20250623_140000"
    
    print(f"\n1. Создана тестовая история диалога:")
    print(f"   - ID лида: {test_lead_id}")
    print(f"   - Количество сообщений: {len(test_history)}")
    
    # Выводим диалог для просмотра
    print(f"\n2. История диалога:")
    print("-" * 50)
    for msg in test_history:
        role = "МЕНЕДЖЕР" if msg["role"] == "assistant" else "КЛИЕНТ"
        print(f"{role}: {msg['content']}")
    print("-" * 50)
    
    # Инициализируем постпроцессор
    print(f"\n3. Инициализация постпроцессора...")
    processor = PostCallProcessor()
    
    # Запускаем постобработку
    print(f"\n4. Запуск постобработки...")
    await processor._process_call_history(test_lead_id, test_history)
    
    print(f"\n5. Постобработка завершена!")
    print(f"   Результат должен быть сохранен в папке tmp/")
    
    # Ищем созданный файл результата
    import glob
    pattern = os.path.join(processor.tmp_dir, f"post_analysis_lead_{test_lead_id}_*.json")
    result_files = glob.glob(pattern)
    
    if result_files:
        latest_file = max(result_files, key=os.path.getctime)
        print(f"   Найден файл результата: {os.path.basename(latest_file)}")
        
        # Читаем и выводим результат
        import json
        with open(latest_file, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        print(f"\n6. РЕЗУЛЬТАТ АНАЛИЗА:")
        print("=" * 50)
        print(f"Модель: {result.get('model_used', 'неизвестно')}")
        print(f"Временная метка: {result.get('timestamp', 'неизвестно')}")
        print()
        
        analysis = result.get('analysis', {})
        if analysis:
            print("Извлеченные данные:")
            for field_id, value in analysis.items():
                print(f"  {field_id}: {value}")
        else:
            print("Анализ не содержит данных")
        
        print("=" * 50)
        
    else:
        print(f"   ОШИБКА: Файл результата не найден!")

def main():
    """
    Точка входа в программу
    """
    try:
        # Запускаем тест в асинхронном режиме
        asyncio.run(test_post_processor())
        
    except KeyboardInterrupt:
        print("\nТест прерван пользователем")
    except Exception as e:
        print(f"\nОШИБКА при выполнении теста: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
