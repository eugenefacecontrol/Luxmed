import os
import requests
import json
from urllib.parse import urljoin
import re

# Конфигурация
BROKUL_BASE_URL = "https://dietyodbrokula.pl"
BROKUL_EMAIL = os.environ.get("BROKUL_EMAIL", "ekaterinafreese@gmail.com")
BROKUL_PASS = os.environ.get("KatyaPass")

class BrokulAPI:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.csrf_token = None
        self.is_logged_in = False

    def get_csrf_token(self):
        """Получает CSRF токен со страницы логина"""
        try:
            response = self.session.get(f"{BROKUL_BASE_URL}/customer/account/login/")
            response.raise_for_status()
            
            # Ищем CSRF токен в HTML
            csrf_pattern = r'name="form_key" value="([^"]+)"'
            match = re.search(csrf_pattern, response.text)
            if match:
                self.csrf_token = match.group(1)
                print(f"CSRF токен получен: {self.csrf_token}")
                return True
            else:
                print("CSRF токен не найден")
                return False
        except Exception as e:
            print(f"Ошибка при получении CSRF токена: {e}")
            return False

    def login(self):
        """Выполняет вход в систему"""
        if not BROKUL_PASS:
            raise Exception("BROKUL_PASS environment variable is not set")

        # Получаем CSRF токен
        if not self.get_csrf_token():
            raise Exception("Не удалось получить CSRF токен")

        # Данные для входа
        login_data = {
            'login[username]': BROKUL_EMAIL,
            'login[password]': BROKUL_PASS,
            'form_key': self.csrf_token,
            'send': ''
        }

        try:
            # Выполняем POST запрос для входа
            response = self.session.post(
                f"{BROKUL_BASE_URL}/customer/account/loginPost/",
                data=login_data,
                allow_redirects=True
            )
            response.raise_for_status()

            # Проверяем, что вход выполнен успешно
            if "customer/account/" in response.url or "customer/diets/" in response.url:
                self.is_logged_in = True
                print("Вход выполнен успешно!")
                return True
            else:
                print("Вход не выполнен. Проверьте логин и пароль.")
                return False

        except Exception as e:
            print(f"Ошибка при входе: {e}")
            return False

    def get_menu_item(self, item_id):
        """Получает данные конкретного пункта меню"""
        if not self.is_logged_in:
            if not self.login():
                raise Exception("Не удалось войти в систему")

        url = f"{BROKUL_BASE_URL}/customer/diets/menu/item/{item_id}/"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            print(f"Статус ответа: {response.status_code}")
            print(f"URL: {response.url}")
            
            # Сохраняем HTML для анализа
            with open(f"brokul_item_{item_id}.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            
            # Пытаемся извлечь данные из HTML
            data = self.extract_menu_data(response.text)
            
            return {
                'status_code': response.status_code,
                'url': response.url,
                'html_saved': f"brokul_item_{item_id}.html",
                'extracted_data': data
            }
            
        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            return {'error': str(e)}

    def extract_menu_data(self, html_content):
        """Извлекает данные меню из HTML"""
        data = {}
        
        try:
            # Ищем название блюда
            title_pattern = r'<h1[^>]*>([^<]+)</h1>'
            title_match = re.search(title_pattern, html_content)
            if title_match:
                data['title'] = title_match.group(1).strip()
            
            # Ищем описание
            desc_pattern = r'<div[^>]*class="[^"]*description[^"]*"[^>]*>([^<]+)</div>'
            desc_match = re.search(desc_pattern, html_content)
            if desc_match:
                data['description'] = desc_match.group(1).strip()
            
            # Ищем калории
            calories_pattern = r'калории[:\s]*(\d+)'
            calories_match = re.search(calories_pattern, html_content, re.IGNORECASE)
            if calories_match:
                data['calories'] = calories_match.group(1)
            
            # Ищем белки, жиры, углеводы
            macros_pattern = r'(белки|жиры|углеводы)[:\s]*(\d+(?:\.\d+)?)'
            macros_matches = re.findall(macros_pattern, html_content, re.IGNORECASE)
            for macro, value in macros_matches:
                data[macro.lower()] = value
            
            # Ищем ингредиенты
            ingredients_pattern = r'ингредиенты[:\s]*([^<]+)'
            ingredients_match = re.search(ingredients_pattern, html_content, re.IGNORECASE)
            if ingredients_match:
                data['ingredients'] = ingredients_match.group(1).strip()
                
        except Exception as e:
            print(f"Ошибка при извлечении данных: {e}")
        
        return data

    def get_menu_list(self):
        """Получает список всех пунктов меню"""
        if not self.is_logged_in:
            if not self.login():
                raise Exception("Не удалось войти в систему")

        url = f"{BROKUL_BASE_URL}/customer/diets/menu/"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Ищем ссылки на пункты меню
            menu_links = re.findall(r'href="([^"]*customer/diets/menu/item/\d+/[^"]*)"', response.text)
            
            return {
                'status_code': response.status_code,
                'menu_links': menu_links
            }
            
        except Exception as e:
            print(f"Ошибка при получении списка меню: {e}")
            return {'error': str(e)}

def main():
    api = BrokulAPI()
    
    # Тестируем получение конкретного пункта меню
    item_id = "12799611"
    print(f"Получаем данные для пункта меню {item_id}...")
    
    result = api.get_menu_item(item_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Также получаем список всех пунктов меню
    print("\nПолучаем список всех пунктов меню...")
    menu_list = api.get_menu_list()
    print(json.dumps(menu_list, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 