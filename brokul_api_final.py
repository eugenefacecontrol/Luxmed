import os
import requests
import re
import json
import datetime
from urllib.parse import urljoin, urlparse
import time

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

class BrokulFinalAPI:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://dietyodbrokula.pl"
        self.login_url = f"{self.base_url}/customer/account/login/"
        self.login_post_url = f"{self.base_url}/customer/account/loginPost/"
        
        # Enhanced headers to better mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
        })
    
    def get_csrf_token(self, html_content):
        """Extract CSRF token from HTML content"""
        # Based on debug output, we know the exact pattern
        pattern = r'name="form_key"\s+value="([^"]+)"'
        matches = re.findall(pattern, html_content)
        if matches:
            print(f"Found CSRF token: {matches[0]}")
            return matches[0]
        
        print("No CSRF token found")
        return None
    
    def login(self, email, password):
        """Perform login using the correct API approach"""
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
                print("❌ No CSRF token found - cannot proceed")
                return False
            
            # Prepare login data with correct field names
            login_data = {
                'form_key': csrf_token,
                'login[username]': email,
                'login[password]': password,
            }
            
            print(f"Login data: {json.dumps(login_data, indent=2)}")
            
            # Update headers for POST request
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': self.login_url,
            })
            
            print("Step 2: Submitting login form...")
            login_response = self.session.post(self.login_post_url, data=login_data, allow_redirects=True)
            print(f"Login response status: {login_response.status_code}")
            print(f"Final URL after login: {login_response.url}")
            
            # Check if login was successful
            if "customer/account/login" not in login_response.url:
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
            
            # Try multiple possible menu URLs
            menu_urls = [
                f"{self.base_url}/menu/",
                f"{self.base_url}/diet/",
                f"{self.base_url}/customer/account/",
                f"{self.base_url}/",
            ]
            
            for menu_url in menu_urls:
                try:
                    print(f"Trying menu URL: {menu_url}")
                    response = self.session.get(menu_url)
                    response.raise_for_status()
                    
                    print(f"Menu page status: {response.status_code}")
                    print(f"Menu page URL: {response.url}")
                    
                    # Check if we can access the menu
                    success_indicators = [
                        "menu" in response.url.lower(),
                        "diet" in response.url.lower(),
                        "account" in response.url.lower() and "login" not in response.url.lower(),
                        "dashboard" in response.url.lower(),
                    ]
                    
                    if any(success_indicators):
                        print("✅ Successfully accessed menu page!")
                        return True
                        
                except Exception as e:
                    print(f"Failed to access {menu_url}: {e}")
                    continue
            
            print("❌ Failed to access any menu page")
            return False
                
        except Exception as e:
            print(f"Menu access error: {e}")
            return False
    
    def extract_menu_items(self, html_content):
        """Extract menu items from HTML content"""
        menu_items = []
        
        # Look for common menu item patterns
        patterns = [
            r'<div[^>]*class="[^"]*menu[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*item[^"]*"[^>]*>(.*?)</div>',
            r'<li[^>]*class="[^"]*menu[^"]*"[^>]*>(.*?)</li>',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                # Clean up the HTML
                clean_text = re.sub(r'<[^>]+>', '', match).strip()
                if clean_text:
                    menu_items.append(clean_text)
        
        return menu_items

def test_brokul_final_api():
    """Test Brokul login using final API approach"""
    if not BROKUL_PASS:
        print("❌ BROKUL_PASS environment variable is not set")
        log_run("FAIL", "BROKUL_PASS not set")
        return
    
    api = BrokulFinalAPI()
    
    try:
        # Attempt login
        login_success = api.login(BROKUL_EMAIL, BROKUL_PASS)
        
        if login_success:
            # Try to access menu
            menu_success = api.get_menu_data()
            
            if menu_success:
                message = f"✅ Brokul Final API test passed! Successfully logged in and accessed menu."
                send_discord_message(message)
                log_run("PASS", "Final API login and menu access successful")
                print("✅ Test passed!")
            else:
                message = f"⚠️ Brokul Final API test partially successful - login worked but menu access failed"
                send_discord_message(message)
                log_run("PARTIAL", "Login successful but menu access failed")
                print("⚠️ Test partially successful")
        else:
            message = f"❌ Brokul Final API test failed - login unsuccessful"
            send_discord_message(message)
            log_run("FAIL", "Login failed")
            print("❌ Test failed")
            
    except Exception as e:
        error_msg = f"❌ Brokul Final API test error: {str(e)}"
        send_discord_message(error_msg)
        log_run("FAIL", str(e))
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_brokul_final_api() 