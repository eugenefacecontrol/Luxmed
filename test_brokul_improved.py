import os
import requests
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import datetime
import json

LOG_FILE = "C:/Source/Luxmed/brokul_test_log.txt"

# Set your Discord webhook URL here or via environment variable
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

def extract_csrf_token(html_content):
    """Extract CSRF token from HTML content using multiple patterns"""
    patterns = [
        r'name="form_key"\s+value="([^"]+)"',
        r'name="csrf_token"\s+value="([^"]+)"',
        r'name="token"\s+value="([^"]+)"',
        r'<input[^>]*name="[^"]*key[^"]*"[^>]*value="([^"]+)"',
        r'<input[^>]*value="([^"]+)"[^>]*name="[^"]*key[^"]*"',
        r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
        r'<meta[^>]*content="([^"]+)"[^>]*name="csrf-token"',
        r'window\.csrf_token\s*=\s*["\']([^"\']+)["\']',
        r'window\.form_key\s*=\s*["\']([^"\']+)["\']',
        r'data-csrf="([^"]+)"',
        r'data-token="([^"]+)"',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def extract_form_data(html_content):
    """Extract all form input fields and their values"""
    form_data = {}
    
    # Find all input fields
    input_pattern = r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"'
    inputs = re.findall(input_pattern, html_content, re.IGNORECASE)
    
    for name, value in inputs:
        if name and name not in ['login[username]', 'password']:  # Skip login fields
            form_data[name] = value
    
    # Find all hidden fields
    hidden_pattern = r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"'
    hidden_inputs = re.findall(hidden_pattern, html_content, re.IGNORECASE)
    
    for name, value in hidden_inputs:
        if name:
            form_data[name] = value
    
    return form_data

def test_brokul_improved():
    """Improved Brokul test with proper CSRF token handling"""
    
    # First, try to get the login page and extract CSRF token
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    try:
        # Step 1: Get the login page
        print("Step 1: Getting login page...")
        response = session.get("https://dietyodbrokula.pl/customer/account/login/")
        response.raise_for_status()
        
        # Save the login page HTML for debugging
        with open("login_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Login page saved to login_page.html")
        
        # Extract CSRF token and form data
        html_content = response.text
        csrf_token = extract_csrf_token(html_content)
        form_data = extract_form_data(html_content)
        
        print(f"Found CSRF token: {csrf_token}")
        print(f"Found form data: {form_data}")
        
        # Prepare login data
        login_data = {
            'login[username]': BROKUL_EMAIL,
            'password': BROKUL_PASS,
        }
        
        # Add CSRF token if found
        if csrf_token:
            login_data['form_key'] = csrf_token
        
        # Add all other form fields
        login_data.update(form_data)
        
        print(f"Login data prepared: {login_data}")
        
        # Step 2: Submit login form
        print("Step 2: Submitting login form...")
        login_response = session.post(
            "https://dietyodbrokula.pl/customer/account/loginPost/",
            data=login_data,
            allow_redirects=True
        )
        
        # Save the login response for debugging
        with open("login_response.html", "w", encoding="utf-8") as f:
            f.write(login_response.text)
        print("Login response saved to login_response.html")
        
        # Check if login was successful
        if "Nieprawidłowy klucz formularza" in login_response.text:
            print("Login failed: Invalid form key")
            log_run("FAIL", "Invalid form key")
            return False
        
        if "customer/account/login" in login_response.url:
            print("Login failed: Redirected back to login page")
            log_run("FAIL", "Redirected to login page")
            return False
        
        print(f"Login response URL: {login_response.url}")
        print(f"Login response status: {login_response.status_code}")
        
        # Step 3: Try to access menu page
        print("Step 3: Accessing menu page...")
        menu_response = session.get("https://dietyodbrokula.pl/customer/account/")
        
        # Save menu response for debugging
        with open("menu_response.html", "w", encoding="utf-8") as f:
            f.write(menu_response.text)
        print("Menu response saved to menu_response.html")
        
        # Check if we can access the menu
        if "Sprawdź menu" in menu_response.text or "menu" in menu_response.text.lower():
            print("Successfully accessed menu page!")
            send_discord_message(f"✅ Brokul test passed! Menu accessible at: {menu_response.url}")
            log_run("PASS", f"Menu accessible at: {menu_response.url}")
            return True
        else:
            print("Failed to access menu page")
            log_run("FAIL", "Menu page not accessible")
            return False
            
    except Exception as e:
        print(f"Test failed with exception: {e}")
        log_run("FAIL", str(e))
        return False

def test_brokul_selenium_fallback():
    """Fallback to Selenium if requests approach fails"""
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    # options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1032')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    
    try:
        print("Using Selenium fallback...")
        
        # Step 1: Open Brokul website
        driver.get("https://dietyodbrokula.pl/")
        driver.set_window_size(1920, 1032)

        # Step 2: Click login link
        login_link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".header__customer-link-text")))
        login_link.click()

        # Step 3: Type email
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "login[username]")))
        email_input.clear()
        email_input.send_keys(BROKUL_EMAIL)

        if not BROKUL_PASS:
            raise Exception("BROKUL_PASS environment variable is not set")

        # Step 4: Type password
        password_input = wait.until(EC.presence_of_element_located((By.ID, "password")))
        password_input.clear()
        password_input.send_keys(BROKUL_PASS)

        # Step 5: Click login button
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".account-form__button")))
        login_btn.click()

        # Wait for login to complete
        time.sleep(3)

        # Step 6: Try to access menu
        try:
            menu_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Sprawdź menu")))
            menu_link.click()
        except:
            # Try to navigate directly to menu page
            driver.get("https://dietyodbrokula.pl/customer/account/")

        # Wait for page to load
        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        
        # Check if we're on a menu page
        current_url = driver.current_url
        page_source = driver.page_source
        
        if "menu" in page_source.lower() or "diet" in page_source.lower():
            print("Selenium test passed!")
            send_discord_message(f"✅ Brokul Selenium test passed! URL: {current_url}")
            log_run("PASS", f"Selenium URL: {current_url}")
            return True
        else:
            print("Selenium test failed - no menu content found")
            log_run("FAIL", "Selenium - no menu content")
            return False
            
    except Exception as e:
        print(f"Selenium test failed: {e}")
        log_run("FAIL", f"Selenium: {str(e)}")
        return False
    finally:
        driver.quit()

if __name__ == "__main__":
    print("Starting improved Brokul test...")
    
    # Try the improved requests approach first
    if test_brokul_improved():
        print("Requests approach succeeded!")
    else:
        print("Requests approach failed, trying Selenium fallback...")
        test_brokul_selenium_fallback() 