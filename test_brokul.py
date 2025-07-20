import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import datetime
import re

LOG_FILE = "C:/Source/Luxmed/brokul_test_log.txt"

# Set your Discord webhook URL here or via environment variable
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL_BROKUL')
BROKUL_EMAIL = os.environ.get("BROKUL_EMAIL", "ekaterinafreese@gmail.com")
BROKUL_PASS = os.environ.get("KatyaPass")
ANTHROPIC_API_KEY = os.environ.get("AnthropicKey")

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

        match = re.search(r'"method":"(.*?)","selector":"(.*?)"', message)

        if match:
            method = match.group(1)
            selector = match.group(2)
            print(f"Method: {method}")
            print(f"Selector: {selector}")
            f.write(f"{timestamp} | {result} | {selector}\n")
        else:
            f.write(f"{timestamp} | {result}\n")

def test_brokul():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1032')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    try:
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

        # Step 6: Click "Sprawdź menu" (Check menu) link
        menu_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Sprawdź menu")))
        menu_link.click()

        # Wait for page to load and verify we're on the menu page
        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        
        # Verify we're on the menu page by checking for menu-related elements
        wait.until(EC.presence_of_element_located((By.XPATH, "//body[contains(@class, 'menu') or contains(@class, 'diet')]")))

        # If we reach here, test passed
        current_url = driver.current_url
        send_discord_message(f"✅ Brokul test passed! Current page URL: {current_url}")
        log_run("PASS", f"URL: {current_url}")
        print("Test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        log_run("FAIL", str(e))
    finally:
        driver.quit()


if __name__ == "__main__":
    test_brokul() 