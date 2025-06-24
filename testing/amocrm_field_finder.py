"""
Универсальный скрипт для поиска и получения информации о полях AmoCRM
Позволяет найти поле по названию и получить его подробную информацию
"""

import os
import sys
import json
from dotenv import load_dotenv

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from crm.crm_api import AmoCRMClient

def search_fields_by_name(search_term):
    """
    Ищет поля AmoCRM по названию (частичное совпадение)
    
    Args:
        search_term (str): Поисковый термин для поиска в названиях полей
    
    Returns:
        list: Список найденных полей
    """
    load_dotenv()
    
    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    access_token = os.getenv("AMOCRM_ACCESS_TOKEN")
    
    if not subdomain or not access_token:
        print("ОШИБКА: Не найдены переменные окружения AMOCRM_SUBDOMAIN и/или AMOCRM_ACCESS_TOKEN")
        return None
    
    try:
        client = AmoCRMClient()
        print(f"Подключаемся к AmoCRM ({subdomain}.amocrm.ru)...")
        
        print("Получаем список всех полей лидов...")
        response = client.get_lead_custom_fields()
        
        if not response or '_embedded' not in response:
            print("Не удалось получить поля из AmoCRM")
            return None
        
        custom_fields = response['_embedded'].get('custom_fields', [])
        print(f"Найдено {len(custom_fields)} кастомных полей")
        
        search_term_lower = search_term.lower()
        found_fields = []
        
        for field in custom_fields:
            field_name = field.get('name', '').lower()
            if search_term_lower in field_name:
                found_fields.append({
                    'id': field.get('id'),
                    'name': field.get('name'),
                    'type': field.get('type'),
                    'code': field.get('code'),
                    'sort': field.get('sort'),
                    'is_required': field.get('is_required', False)
                })
        
        return found_fields, custom_fields
        
    except Exception as e:
        print(f"ОШИБКА при работе с AmoCRM: {e}")
        return None, None

def get_field_details(field_id):
    """
    Получает подробную информацию о поле по его ID
    
    Args:
        field_id (int): ID поля AmoCRM
    
    Returns:
        dict: Подробная информация о поле
    """
    try:
        client = AmoCRMClient()
        print(f"Получаем подробную информацию о поле с ID: {field_id}")
        
        field_info = client.get_lead_custom_field_by_id(field_id)
        
        if not field_info:
            print("Не удалось получить информацию о поле")
            return None
        
        return field_info
        
    except Exception as e:
        print(f"Ошибка при получении информации о поле: {e}")
        return None

def display_field_info(field_info):
    """
    Выводит подробную информацию о поле в удобном формате
    
    Args:
        field_info (dict): Информация о поле из AmoCRM API
    """
    print(f"Информация о поле:")
    print(f"  ID: {field_info.get('id')}")
    print(f"  Название: '{field_info.get('name')}'")
    print(f"  Тип: {field_info.get('type')}")
    print(f"  Код: {field_info.get('code', 'Не указан')}")
    print(f"  Обязательное: {'Да' if field_info.get('is_required') else 'Нет'}")
    print(f"  Сортировка: {field_info.get('sort', 'Не указана')}")
    
    # Если поле типа select или multiselect, выводим варианты
    enums = field_info.get('enums')
    if enums:
        print(f"\nДоступные варианты ({len(enums)} штук):")
        # Сортируем по полю sort
        sorted_enums = sorted(enums, key=lambda x: x.get('sort', 0))
        for i, enum_item in enumerate(sorted_enums, 1):
            print(f"  {i:2d}. {enum_item.get('value')} (ID: {enum_item.get('id')})")
    
    required_statuses = field_info.get('required_statuses', [])
    if required_statuses:
        print(f"\nПоле обязательно для {len(required_statuses)} статуса(ов)")

    print(f"\nПолная информация в JSON:")
    print(json.dumps(field_info, indent=2, ensure_ascii=False))

def select_field_from_list(found_fields):
    """
    Позволяет пользователю выбрать поле из найденных
    
    Args:
        found_fields (list): Список найденных полей
    
    Returns:
        dict: Выбранное поле или None
    """
    if not found_fields:
        return None
    
    if len(found_fields) == 1:
        field = found_fields[0]
        print(f"Найдено одно поле: '{field['name']}' (ID: {field['id']})")
        return field

    print(f"\nНайдено {len(found_fields)} полей. Выберите нужное:")
    for i, field in enumerate(found_fields, 1):
        req_marker = " [ОБЯЗАТЕЛЬНОЕ]" if field.get('is_required') else ""
        print(f"  {i:2d}. {field['name']} (ID: {field['id']}, Тип: {field['type']}){req_marker}")
    
    try:
        choice = input(f"\nВведите номер поля (1-{len(found_fields)}): ")
        if choice.lower() in ['q', 'quit', 'exit', 'выход']:
            print("Операция отменена")
            return None
        
        choice_num = int(choice) - 1
        if 0 <= choice_num < len(found_fields):
            selected_field = found_fields[choice_num]
            print(f"Выбрано поле: '{selected_field['name']}' (ID: {selected_field['id']})")
            return selected_field
        else:
            print("Неверный номер поля")
            return None
    except (ValueError, KeyboardInterrupt):
        print("Операция отменена")
        return None

def show_similar_fields(custom_fields, search_term, limit=10):
    """
    Показывает похожие поля при неуспешном поиске
    
    Args:
        custom_fields (list): Все поля AmoCRM
        search_term (str): Поисковый термин
        limit (int): Максимальное количество полей для показа
    """
    print(f"\nВозможно, вы искали одно из этих полей:")
    
    # Показываем случайные поля или поля, содержащие хотя бы одну букву из поискового термина
    suggested_fields = []
    search_chars = set(search_term.lower())
    
    for field in custom_fields[:50]:  # Берем первые 50 полей
        field_name = field.get('name', '').lower()
        if any(char in field_name for char in search_chars):
            suggested_fields.append(field)
    
    # Если не нашли по символам, показываем первые поля
    if not suggested_fields:
        suggested_fields = custom_fields[:limit]
    else:
        suggested_fields = suggested_fields[:limit]
    
    for i, field in enumerate(suggested_fields, 1):
        print(f"  {i:2d}. '{field.get('name')}' (ID: {field.get('id')}, Тип: {field.get('type')})")

def main():
    """
    Основная функция скрипта
    """
    print("Универсальный поиск полей AmoCRM")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        search_term = ' '.join(sys.argv[1:])
        print(f"Поиск полей по запросу: '{search_term}'")
    else:
        search_term = input("Введите название поля для поиска: ").strip()
        if not search_term:
            print("Поисковый запрос не может быть пустым")
            sys.exit(1)
    
    print("=" * 50)
    
    # Ищем поля
    result = search_fields_by_name(search_term)
    if result is None:
        sys.exit(1)
    
    found_fields, all_fields = result
    
    if not found_fields:
        print(f"Поля с названием '{search_term}' не найдены")
        show_similar_fields(all_fields, search_term)
        print("\nПопробуйте изменить поисковый запрос")
        sys.exit(1)
    
    selected_field = select_field_from_list(found_fields)
    if not selected_field:
        sys.exit(1)
    
    print("\n" + "=" * 50)
    field_details = get_field_details(selected_field['id'])
    
    if field_details:
        display_field_info(field_details)
        print("\n" + "=" * 50)
        print(f"РЕЗУЛЬТАТ: ID поля '{field_details.get('name')}' = {field_details.get('id')}")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("Не удалось получить подробную информацию о поле")
        print("=" * 50)
        sys.exit(1)

if __name__ == "__main__":
    main()
