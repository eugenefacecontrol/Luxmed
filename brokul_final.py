import os
import requests
import json
import re
from urllib.parse import urljoin

# Конфигурация
BROKUL_EMAIL = os.environ.get("BROKUL_EMAIL", "ekaterinafreese@gmail.com")
BROKUL_PASS = os.environ.get("KatyaPass")

def get_brokul_menu_item(item_id):
    """
    Получает данные пункта меню Brokul с правильной обработкой сессий
    """
    session = requests.Session()
    
    # Настройка заголовков как у браузера
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    })
    
    try:
        # Шаг 1: Открываем главную страницу для получения cookies
        print("1. Открываем главную страницу...")
        response = session.get("https://dietyodbrokula.pl/")
        response.raise_for_status()
        print(f"   Статус: {response.status_code}")
        
        # Шаг 2: Получаем страницу логина
        print("2. Получаем страницу логина...")
        login_page = session.get("https://dietyodbrokula.pl/customer/account/login/")
        login_page.raise_for_status()
        print(f"   Статус: {login_page.status_code}")
        
        # Сохраняем страницу логина для анализа
        with open("login_page.html", "w", encoding="utf-8") as f:
            f.write(login_page.text)
        print("   HTML сохранен в login_page.html")
        
        # Шаг 3: Извлекаем CSRF токен
        print("3. Извлекаем CSRF токен...")
        csrf_patterns = [
            r'name="form_key" value="([^"]+)"',
            r'name="csrf" value="([^"]+)"',
            r'name="_token" value="([^"]+)"',
            r'<input[^>]*name="[^"]*token[^"]*"[^>]*value="([^"]+)"',
        ]
        
        csrf_token = None
        for pattern in csrf_patterns:
            match = re.search(pattern, login_page.text)
            if match:
                csrf_token = match.group(1)
                print(f"   Найден CSRF токен: {csrf_token}")
                break
        
        if not csrf_token:
            print("   CSRF токен не найден, пробуем без него")
        
        # Шаг 4: Выполняем вход
        print("4. Выполняем вход...")
        if not BROKUL_PASS:
            raise Exception("BROKUL_PASS environment variable is not set")
        
        login_data = {
            'login[username]': BROKUL_EMAIL,
            'login[password]': BROKUL_PASS,
        }
        
        if csrf_token:
            login_data['form_key'] = csrf_token
        
        login_response = session.post(
            "https://dietyodbrokula.pl/customer/account/loginPost/",
            data=login_data,
            allow_redirects=True
        )
        login_response.raise_for_status()
        
        print(f"   Статус входа: {login_response.status_code}")
        print(f"   URL после входа: {login_response.url}")
        
        # Сохраняем результат входа
        with open("login_result.html", "w", encoding="utf-8") as f:
            f.write(login_response.text)
        print("   Результат входа сохранен в login_result.html")
        
        # Шаг 5: Проверяем, успешен ли вход
        if "customer/account/" in login_response.url or "customer/diets/" in login_response.url:
            print("✅ Вход успешен!")
            
            # Шаг 6: Переходим на страницу меню
            print("5. Переходим на страницу меню...")
            menu_response = session.get("https://dietyodbrokula.pl/customer/diets/menu/")
            menu_response.raise_for_status()
            print(f"   Статус меню: {menu_response.status_code}")
            
            # Шаг 7: Получаем конкретный пункт меню
            print(f"6. Получаем пункт меню {item_id}...")
            item_url = f"https://dietyodbrokula.pl/customer/diets/menu/item/{item_id}/"
            item_response = session.get(item_url)
            item_response.raise_for_status()
            
            print(f"   Статус пункта меню: {item_response.status_code}")
            print(f"   URL пункта меню: {item_response.url}")
            
            # Сохраняем HTML
            html_filename = f"brokul_item_{item_id}.html"
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(item_response.text)
            
            print(f"   HTML сохранен в {html_filename}")
            
            # Извлекаем данные из HTML
            extracted_data = extract_data_from_html(item_response.text)
            
            return {
                'success': True,
                'status_code': item_response.status_code,
                'url': item_response.url,
                'html_file': html_filename,
                'extracted_data': extracted_data,
                'session_cookies': dict(session.cookies)
            }
        else:
            print("❌ Вход не удался")
            return {
                'success': False,
                'error': 'Login failed',
                'login_url': login_response.url,
                'login_status': login_response.status_code
            }
            
    except Exception as e:
        print(f"Ошибка: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def extract_data_from_html(html_content):
    """
    Извлекает данные из HTML страницы
    """
    data = {}
    
    try:
        # Ищем заголовок страницы
        title_pattern = r'<title[^>]*>([^<]+)</title>'
        title_match = re.search(title_pattern, html_content)
        if title_match:
            data['page_title'] = title_match.group(1).strip()
        
        # Ищем основной заголовок
        h1_pattern = r'<h1[^>]*>([^<]+)</h1>'
        h1_match = re.search(h1_pattern, html_content)
        if h1_match:
            data['main_title'] = h1_match.group(1).strip()
        
        # Ищем описание
        desc_patterns = [
            r'<div[^>]*class="[^"]*description[^"]*"[^>]*>([^<]+)</div>',
            r'<p[^>]*class="[^"]*description[^"]*"[^>]*>([^<]+)</p>',
            r'<div[^>]*class="[^"]*desc[^"]*"[^>]*>([^<]+)</div>'
        ]
        
        for pattern in desc_patterns:
            desc_match = re.search(pattern, html_content)
            if desc_match:
                data['description'] = desc_match.group(1).strip()
                break
        
        # Ищем калории
        calories_patterns = [
            r'калории[:\s]*(\d+)',
            r'kcal[:\s]*(\d+)',
            r'kalorie[:\s]*(\d+)',
            r'kalorii[:\s]*(\d+)'
        ]
        
        for pattern in calories_patterns:
            calories_match = re.search(pattern, html_content, re.IGNORECASE)
            if calories_match:
                data['calories'] = calories_match.group(1)
                break
        
        # Ищем макронутриенты
        macros_patterns = [
            r'(белки|жиры|углеводы)[:\s]*(\d+(?:\.\d+)?)',
            r'(protein|fat|carbohydrates)[:\s]*(\d+(?:\.\d+)?)',
            r'(białko|tłuszcz|węglowodany)[:\s]*(\d+(?:\.\d+)?)'
        ]
        
        for pattern in macros_patterns:
            macros_matches = re.findall(pattern, html_content, re.IGNORECASE)
            for macro, value in macros_matches:
                data[macro.lower()] = value
        
        # Ищем ингредиенты
        ingredients_patterns = [
            r'ингредиенты[:\s]*([^<]+)',
            r'ingredients[:\s]*([^<]+)',
            r'składniki[:\s]*([^<]+)'
        ]
        
        for pattern in ingredients_patterns:
            ingredients_match = re.search(pattern, html_content, re.IGNORECASE)
            if ingredients_match:
                data['ingredients'] = ingredients_match.group(1).strip()
                break
        
        # Ищем все текстовые блоки для анализа
        text_blocks = re.findall(r'<[^>]*>([^<]{10,})</[^>]*>', html_content)
        data['text_blocks'] = [block.strip() for block in text_blocks if len(block.strip()) > 10][:10]
        
        # Ищем все ссылки на изображения
        img_pattern = r'<img[^>]*src="([^"]+)"'
        images = re.findall(img_pattern, html_content)
        data['images'] = images[:5]  # Первые 5 изображений
        
    except Exception as e:
        print(f"Ошибка при извлечении данных: {e}")
    
    return data

def get_menu_list():
    """
    Получает список всех пунктов меню
    """
    session = requests.Session()
    
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    try:
        # Сначала входим в систему
        login_result = get_brokul_menu_item("12799611")  # Используем существующую функцию для входа
        
        if not login_result['success']:
            return {'error': 'Login failed', 'details': login_result}
        
        # Получаем список меню
        menu_url = "https://dietyodbrokula.pl/customer/diets/menu/"
        menu_response = session.get(menu_url)
        menu_response.raise_for_status()
        
        # Ищем ссылки на пункты меню
        menu_links = re.findall(r'href="([^"]*customer/diets/menu/item/\d+/[^"]*)"', menu_response.text)
        
        # Извлекаем ID пунктов меню
        menu_ids = []
        for link in menu_links:
            id_match = re.search(r'/item/(\d+)/', link)
            if id_match:
                menu_ids.append(id_match.group(1))
        
        return {
            'success': True,
            'menu_links': menu_links,
            'menu_ids': menu_ids,
            'total_items': len(menu_ids)
        }
        
    except Exception as e:
        return {'error': str(e)}

def main():
    item_id = "12799611"
    print(f"Получаем данные для пункта меню {item_id}...")
    
    result = get_brokul_menu_item(item_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result['success']:
        print(f"\n✅ Данные успешно получены!")
        print(f"📁 HTML файл: {result['html_file']}")
        print(f"📊 Извлеченные данные:")
        for key, value in result['extracted_data'].items():
            if key != 'text_blocks' and key != 'images':
                print(f"   {key}: {value}")
    else:
        print(f"\n❌ Ошибка: {result.get('error', 'Unknown error')}")
    
    # Также получаем список всех пунктов меню
    print("\n" + "="*50)
    print("Получаем список всех пунктов меню...")
    menu_list = get_menu_list()
    print(json.dumps(menu_list, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 