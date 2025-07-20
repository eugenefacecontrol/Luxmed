import os
import requests
import json
import re

# Конфигурация
BROKUL_EMAIL = os.environ.get("BROKUL_EMAIL", "ekaterinafreese@gmail.com")
BROKUL_PASS = os.environ.get("KatyaPass")

def debug_login_page():
    """
    Отладочная функция для анализа страницы логина
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
    })
    
    try:
        # Получаем страницу логина
        print("Получаем страницу логина...")
        login_page = session.get("https://dietyodbrokula.pl/customer/account/login/")
        login_page.raise_for_status()
        
        # Сохраняем HTML для анализа
        with open("login_page_debug.html", "w", encoding="utf-8") as f:
            f.write(login_page.text)
        
        print(f"HTML сохранен в login_page_debug.html")
        print(f"Статус: {login_page.status_code}")
        print(f"URL: {login_page.url}")
        
        # Ищем все возможные CSRF токены
        csrf_patterns = [
            r'name="form_key" value="([^"]+)"',
            r'name="csrf" value="([^"]+)"',
            r'name="_token" value="([^"]+)"',
            r'name="authenticity_token" value="([^"]+)"',
            r'<input[^>]*name="[^"]*token[^"]*"[^>]*value="([^"]+)"',
            r'<input[^>]*value="([^"]+)"[^>]*name="[^"]*token[^"]*"',
        ]
        
        print("\nПоиск CSRF токенов:")
        for i, pattern in enumerate(csrf_patterns):
            matches = re.findall(pattern, login_page.text)
            if matches:
                print(f"Паттерн {i+1}: {matches}")
            else:
                print(f"Паттерн {i+1}: не найден")
        
        # Ищем все input поля
        input_pattern = r'<input[^>]*>'
        inputs = re.findall(input_pattern, login_page.text)
        print(f"\nНайдено {len(inputs)} input полей:")
        for i, inp in enumerate(inputs[:10]):  # Показываем первые 10
            print(f"{i+1}: {inp}")
        
        # Ищем все формы
        form_pattern = r'<form[^>]*>.*?</form>'
        forms = re.findall(form_pattern, login_page.text, re.DOTALL)
        print(f"\nНайдено {len(forms)} форм:")
        for i, form in enumerate(forms):
            print(f"Форма {i+1}: {form[:200]}...")
        
        # Ищем все скрытые поля
        hidden_pattern = r'<input[^>]*type="hidden"[^>]*>'
        hidden_inputs = re.findall(hidden_pattern, login_page.text)
        print(f"\nНайдено {len(hidden_inputs)} скрытых полей:")
        for i, hidden in enumerate(hidden_inputs):
            print(f"{i+1}: {hidden}")
        
        return {
            'status_code': login_page.status_code,
            'url': login_page.url,
            'html_file': 'login_page_debug.html',
            'input_count': len(inputs),
            'form_count': len(forms),
            'hidden_count': len(hidden_inputs)
        }
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return {'error': str(e)}

def try_different_login_approaches():
    """
    Пробует разные подходы к входу
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
    
    if not BROKUL_PASS:
        print("BROKUL_PASS environment variable is not set")
        return
    
    try:
        # Подход 1: Простой POST без CSRF
        print("\nПодход 1: Простой POST без CSRF...")
        login_data1 = {
            'login[username]': BROKUL_EMAIL,
            'login[password]': BROKUL_PASS,
        }
        
        response1 = session.post(
            "https://dietyodbrokula.pl/customer/account/loginPost/",
            data=login_data1,
            allow_redirects=True
        )
        
        print(f"Статус: {response1.status_code}")
        print(f"URL: {response1.url}")
        
        # Сохраняем результат
        with open("login_attempt1.html", "w", encoding="utf-8") as f:
            f.write(response1.text)
        
        # Проверяем, успешен ли вход
        if "customer/account/" in response1.url or "customer/diets/" in response1.url:
            print("✅ Вход успешен!")
            
            # Пробуем получить пункт меню
            item_id = "12799611"
            item_url = f"https://dietyodbrokula.pl/customer/diets/menu/item/{item_id}/"
            item_response = session.get(item_url)
            
            print(f"Статус получения пункта меню: {item_response.status_code}")
            print(f"URL пункта меню: {item_response.url}")
            
            # Сохраняем HTML
            with open(f"brokul_item_{item_id}.html", "w", encoding="utf-8") as f:
                f.write(item_response.text)
            
            print(f"HTML пункта меню сохранен в brokul_item_{item_id}.html")
            
            return {
                'success': True,
                'method': 'simple_post',
                'item_status': item_response.status_code,
                'item_url': item_response.url,
                'html_file': f"brokul_item_{item_id}.html"
            }
        else:
            print("❌ Вход не удался")
            
            # Подход 2: С получением CSRF токена
            print("\nПодход 2: С получением CSRF токена...")
            
            # Получаем страницу логина
            login_page = session.get("https://dietyodbrokula.pl/customer/account/login/")
            
            # Ищем CSRF токен
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
                    print(f"Найден CSRF токен: {csrf_token}")
                    break
            
            if csrf_token:
                login_data2 = {
                    'login[username]': BROKUL_EMAIL,
                    'login[password]': BROKUL_PASS,
                    'form_key': csrf_token,
                }
                
                response2 = session.post(
                    "https://dietyodbrokula.pl/customer/account/loginPost/",
                    data=login_data2,
                    allow_redirects=True
                )
                
                print(f"Статус с CSRF: {response2.status_code}")
                print(f"URL с CSRF: {response2.url}")
                
                if "customer/account/" in response2.url or "customer/diets/" in response2.url:
                    print("✅ Вход с CSRF успешен!")
                    return {'success': True, 'method': 'with_csrf'}
                else:
                    print("❌ Вход с CSRF не удался")
            
            return {'success': False, 'method': 'both_failed'}
            
    except Exception as e:
        print(f"Ошибка: {e}")
        return {'error': str(e)}

def main():
    print("=== Отладка страницы логина ===")
    debug_result = debug_login_page()
    print(json.dumps(debug_result, indent=2, ensure_ascii=False))
    
    print("\n=== Попытка входа ===")
    login_result = try_different_login_approaches()
    print(json.dumps(login_result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 