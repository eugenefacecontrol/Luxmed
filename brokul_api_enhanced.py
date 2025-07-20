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

class BrokulEnhancedAPI:
    def __init__(self, debug=False):
        self.session = requests.Session()
        self.base_url = "https://dietyodbrokula.pl"
        self.login_url = f"{self.base_url}/customer/account/login/"
        self.debug = debug
        
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
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
        })
    
    def debug_response(self, response, step_name):
        """Debug response details"""
        if not self.debug:
            return
            
        print(f"\n=== {step_name} Debug Info ===")
        print(f"Status Code: {response.status_code}")
        print(f"URL: {response.url}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Cookies: {dict(response.cookies)}")
        
        # Save response content for analysis
        with open(f"debug_{step_name.lower().replace(' ', '_')}.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"Response saved to debug_{step_name.lower().replace(' ', '_')}.html")
    
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
            r'data-csrf="([^"]+)"',
            r'data-token="([^"]+)"',
        ]
        
        for i, pattern in enumerate(csrf_patterns):
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                print(f"Found CSRF token (pattern {i+1}): {matches[0]}")
                return matches[0]
        
        print("No CSRF token found")
        return None
    
    def get_form_action(self, html_content):
        """Extract form action URL from HTML content"""
        form_patterns = [
            r'<form[^>]*action="([^"]*)"[^>]*>',
            r'<form[^>]*>.*?action="([^"]*)"',
        ]
        
        for pattern in form_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if matches:
                action_url = matches[0]
                if action_url.startswith('/'):
                    action_url = urljoin(self.base_url, action_url)
                elif not action_url.startswith('http'):
                    action_url = urljoin(self.base_url, action_url)
                print(f"Found form action: {action_url}")
                return action_url
        
        print(f"No form action found, using default: {self.login_url}")
        return self.login_url
    
    def get_all_form_fields(self, html_content):
        """Extract all form fields from HTML content"""
        input_patterns = [
            r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"[^>]*>',
            r'<input[^>]*value="([^"]*)"[^>]*name="([^"]+)"[^>]*>',
        ]
        
        form_data = {}
        for pattern in input_patterns:
            inputs = re.findall(pattern, html_content, re.IGNORECASE)
            for match in inputs:
                if len(match) == 2:
                    name, value = match
                    form_data[name] = value
                    print(f"Form field: {name} = {value}")
        
        return form_data
    
    def analyze_response_for_errors(self, response):
        """Analyze response for error messages or indicators"""
        html_content = response.text.lower()
        
        error_indicators = [
            'error',
            'invalid',
            'failed',
            'incorrect',
            'wrong',
            'not found',
            'access denied',
            'unauthorized',
        ]
        
        found_errors = []
        for indicator in error_indicators:
            if indicator in html_content:
                # Extract context around the error
                pattern = rf'[^.]*{indicator}[^.]*'
                matches = re.findall(pattern, html_content)
                if matches:
                    found_errors.append(f"{indicator}: {matches[0][:100]}...")
        
        return found_errors
    
    def login(self, email, password):
        """Perform login using enhanced API approach"""
        try:
            print("Step 1: Getting login page...")
            response = self.session.get(self.login_url)
            response.raise_for_status()
            
            self.debug_response(response, "Login Page")
            
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
            
            self.debug_response(login_response, "Login Response")
            
            # Analyze response for errors
            errors = self.analyze_response_for_errors(login_response)
            if errors:
                print(f"Found potential errors in response: {errors}")
            
            # Check if login was successful
            success_indicators = [
                "customer/account" in login_response.url,
                "customer/account/login" not in login_response.url,
                "dashboard" in login_response.url.lower(),
                "account" in login_response.url.lower(),
            ]
            
            if any(success_indicators):
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
                    
                    self.debug_response(response, f"Menu Page {menu_url}")
                    
                    # Check if we can access the menu
                    success_indicators = [
                        "menu" in response.url.lower(),
                        "diet" in response.url.lower(),
                        "account" in response.url.lower(),
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
        # This is a placeholder - you'll need to implement based on the actual HTML structure
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

def test_brokul_enhanced_api():
    """Test Brokul login using enhanced API approach"""
    if not BROKUL_PASS:
        print("❌ BROKUL_PASS environment variable is not set")
        log_run("FAIL", "BROKUL_PASS not set")
        return
    
    api = BrokulEnhancedAPI(debug=True)
    
    try:
        # Attempt login
        login_success = api.login(BROKUL_EMAIL, BROKUL_PASS)
        
        if login_success:
            # Try to access menu
            menu_success = api.get_menu_data()
            
            if menu_success:
                message = f"✅ Brokul Enhanced API test passed! Successfully logged in and accessed menu."
                send_discord_message(message)
                log_run("PASS", "Enhanced API login and menu access successful")
                print("✅ Test passed!")
            else:
                message = f"⚠️ Brokul Enhanced API test partially successful - login worked but menu access failed"
                send_discord_message(message)
                log_run("PARTIAL", "Login successful but menu access failed")
                print("⚠️ Test partially successful")
        else:
            message = f"❌ Brokul Enhanced API test failed - login unsuccessful"
            send_discord_message(message)
            log_run("FAIL", "Login failed")
            print("❌ Test failed")
            
    except Exception as e:
        error_msg = f"❌ Brokul Enhanced API test error: {str(e)}"
        send_discord_message(error_msg)
        log_run("FAIL", str(e))
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_brokul_enhanced_api() 