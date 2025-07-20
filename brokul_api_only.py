import os
import requests
import re
import json
import datetime
from urllib.parse import urljoin, urlparse

LOG_FILE = "C:/Source/Luxmed/brokul_test_log.txt"
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL_BROKUL')
BROKUL_EMAIL = os.environ.get("BROKUL_EMAIL", "ekaterinafreese@gmail.com")
BROKUL_PASS = os.environ.get("KatyaPass")

def send_discord_message(message):
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == 'YOUR_WEBHOOK_URL_HERE':
        print('Webhook URL not set, skipping Discord notification.')
        return
    data = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Discord message: {e}")

def log_run(result, message=""):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().isoformat()
        f.write(f"{timestamp} | {result} | {message}\n")

class BrokulAPI:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://dietyodbrokula.pl"
        self.login_url = f"{self.base_url}/customer/account/login/"
        
        # Set up headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
    
    def get_csrf_token(self, html_content):
        """Extract CSRF token from HTML content using multiple patterns"""
        csrf_patterns = [
            r'name="form_key"\s+value="([^"]+)"',
            r'name="csrf_token"\s+value="([^"]+)"',
            r'name="token"\s+value="([^"]+)"',
            r'<input[^>]*name="[^"]*key[^"]*"[^>]*value="([^"]+)"',
            r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
            r'window\.csrf_token\s*=\s*["\']([^"\']+)["\']',
            r'window\.form_key\s*=\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in csrf_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                print(f"Found CSRF token: {matches[0]}")
                return matches[0]
        
        print("No CSRF token found")
        return None
    
    def get_form_action(self, html_content):
        """Extract form action URL from HTML content"""
        form_pattern = r'<form[^>]*action="([^"]*)"[^>]*>'
        matches = re.findall(form_pattern, html_content)
        if matches:
            action_url = matches[0]
            if action_url.startswith('/'):
                action_url = urljoin(self.base_url, action_url)
            print(f"Found form action: {action_url}")
            return action_url
        return self.login_url
    
    def get_all_form_fields(self, html_content):
        """Extract all form fields from HTML content"""
        input_pattern = r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"[^>]*>'
        inputs = re.findall(input_pattern, html_content)
        
        form_data = {}
        for name, value in inputs:
            form_data[name] = value
            print(f"Form field: {name} = {value}")
        
        return form_data
    
    def login(self, email, password):
        """Perform login using pure API approach"""
        try:
            print("Step 1: Getting login page...")
            response = self.session.get(self.login_url)
            response.raise_for_status()
            
            html_content = response.text
            print(f"Login page status: {response.status_code}")
            print(f"Final URL: {response.url}")
            
            # Extract CSRF token
            csrf_token = self.get_csrf_token(html_content)
            if not csrf_token:
                print("Warning: No CSRF token found, proceeding without it")
            
            # Get form action URL
            form_action = self.get_form_action(html_content)
            
            # Get all existing form fields
            form_data = self.get_all_form_fields(html_content)
            
            # Prepare login data
            login_data = {
                'login[username]': email,
                'login[password]': password,
            }
            
            # Add CSRF token if found
            if csrf_token:
                login_data['form_key'] = csrf_token
            
            # Add any other required form fields
            for field_name, field_value in form_data.items():
                if field_name not in login_data:
                    login_data[field_name] = field_value
            
            print(f"Login data: {json.dumps(login_data, indent=2)}")
            
            # Update headers for POST request
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': self.login_url,
            })
            
            print("Step 2: Submitting login form...")
            login_response = self.session.post(form_action, data=login_data, allow_redirects=True)
            print(f"Login response status: {login_response.status_code}")
            print(f"Final URL after login: {login_response.url}")
            
            # Check if login was successful
            if "customer/account" in login_response.url or "customer/account/login" not in login_response.url:
                print("✅ Login appears successful!")
                return True
            else:
                print("❌ Login failed - still on login page")
                return False
                
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def get_menu_data(self):
        """Get menu data after successful login"""
        try:
            print("Step 3: Accessing menu page...")
            menu_url = f"{self.base_url}/menu/"
            response = self.session.get(menu_url)
            response.raise_for_status()
            
            print(f"Menu page status: {response.status_code}")
            print(f"Menu page URL: {response.url}")
            
            # Check if we can access the menu
            if "menu" in response.url or "diet" in response.url:
                print("✅ Successfully accessed menu page!")
                return True
            else:
                print("❌ Failed to access menu page")
                return False
                
        except Exception as e:
            print(f"Menu access error: {e}")
            return False

def test_brokul_api():
    """Test Brokul login using pure API approach"""
    if not BROKUL_PASS:
        print("❌ BROKUL_PASS environment variable is not set")
        log_run("FAIL", "BROKUL_PASS not set")
        return
    
    api = BrokulAPI()
    
    try:
        # Attempt login
        login_success = api.login(BROKUL_EMAIL, BROKUL_PASS)
        
        if login_success:
            # Try to access menu
            menu_success = api.get_menu_data()
            
            if menu_success:
                message = f"✅ Brokul API test passed! Successfully logged in and accessed menu."
                send_discord_message(message)
                log_run("PASS", "API login and menu access successful")
                print("✅ Test passed!")
            else:
                message = f"⚠️ Brokul API test partially successful - login worked but menu access failed"
                send_discord_message(message)
                log_run("PARTIAL", "Login successful but menu access failed")
                print("⚠️ Test partially successful")
        else:
            message = f"❌ Brokul API test failed - login unsuccessful"
            send_discord_message(message)
            log_run("FAIL", "Login failed")
            print("❌ Test failed")
            
    except Exception as e:
        error_msg = f"❌ Brokul API test error: {str(e)}"
        send_discord_message(error_msg)
        log_run("FAIL", str(e))
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_brokul_api() 