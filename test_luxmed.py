import os
from pathlib import Path
import subprocess
import sys
import time
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

FLAG_FILE = "C:/Source/Luxmed/luxmed_test_passed.flag"
LOG_FILE = "C:/Source/Luxmed/luxmed_test_log.txt"
LUXMED_KEYCHAIN_SERVICE = "Luxmed Patient Portal"
LUXMED_KEYCHAIN_ACCOUNT = "yauhenisheima@gmail.com"
CHROME_PROFILE_DIR = Path(__file__).resolve().parent / ".chrome-profile"

# At the very start of your script:
if os.path.exists(FLAG_FILE):
    print("Test already passed previously. Exiting.")
    sys.exit(0)

# Set your Discord webhook URL here or via environment variable
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL_LUXMED')


def get_luxmed_password():
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            LUXMED_KEYCHAIN_SERVICE,
            "-a",
            LUXMED_KEYCHAIN_ACCOUNT,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Luxmed password was not found in macOS Keychain. "
            "Add it as a generic password with service "
            f"'{LUXMED_KEYCHAIN_SERVICE}' and account "
            f"'{LUXMED_KEYCHAIN_ACCOUNT}'."
        )
    return result.stdout.rstrip("\n")


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

def test_luxmed():
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    # options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1909,1030')
    options.add_argument(f'--user-data-dir={CHROME_PROFILE_DIR}')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    try:
        # Step 1: Open login page
        driver.get("https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/Account/Login?returnUrl=%2FPage%2FDashboard")
        driver.set_window_size(1909, 1030)
        language_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='circle']")))
        language_btn.click()

        # Step 2: Type login
        login_input = wait.until(EC.presence_of_element_located((By.ID, "Login")))
        login_input.clear()
        login_input.send_keys(LUXMED_KEYCHAIN_ACCOUNT)

        # Step 3: Type password
        password_input = wait.until(EC.presence_of_element_located((By.ID, "Password")))
        password_input.clear()
        password_input.send_keys(get_luxmed_password())

        # Step 4: Click login
        login_btn = wait.until(EC.element_to_be_clickable((By.ID, "LoginSubmit")))
        login_btn.click()

        skip_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Skip']")))
        skip_btn.click()

        # Step 5: Click 'Book visit' button
        book_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'btn-book-visit')]")))
        book_btn.click()
        print("Before video cons")
        # Step 6: Click 'Psychiatrist consultation - first visit'
        psychiatrist_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'recent-search-parameters-box')]/div/button[contains(text(), 'Gastroenterologist consultation')]")))
        psychiatrist_btn.click()

        print("After video cons")

        print("Before dropdown")
        dropdown = driver.find_element(By.XPATH, "//app-dropdown-control[@id='language']/div[@class='position-relative']")
        print("After dropdown")
        dropdown.click()
        print("After dropdown clicked")
        print("Before english success")
        english_option = driver.find_element(By.XPATH, "//span[text()='English']")
        english_option.click()
        print("After english success")

        print("Before btn success")
        submitButton = driver.find_element(By.CSS_SELECTOR, ".btn-success")
        print(submitButton.is_displayed())
        print(submitButton.is_enabled())
        if submitButton.is_displayed() and submitButton.is_enabled(): 
            search_btn = wait.until(EC.element_to_be_clickable(submitButton))
            search_btn.click()
        else:
            print("Before Video consultant found")
            videoConsultant = driver.find_element(By.XPATH, "//form[@class='search-parameters-form ng-untouched ng-pristine ng-valid']//form//div[contains(text(), 'Psychiatrist (first visit) - video consultation')]")
            print("Before Video consultant clicked")
            videoConsultant.click()
            print("Video consultant clicked")
            nextButton = driver.find_element(By.XPATH, "//form[@class='search-parameters-form ng-untouched ng-pristine ng-valid']//form//div/button")
            nextButton.click()
            print("Next button clicked")
            search_btn = wait.until(EC.element_to_be_clickable(submitButton))
            search_btn.click()
            print("Search button clicked")
            

        # Step 7: Click 'Search' button


        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")

        wait.until(EC.presence_of_element_located((By.XPATH, "//app-part-of-day-selector/button[contains(text(), 'Entire day')]")))
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@class='days']/div/div[2]/div[2]/span")))

        # Step 8: Assert available day (not '0' or 'x')
        driver.find_element(By.XPATH, "//div[@class='days']/div/div[2]/div[2]/span[text() != '0'][text() != 'x']")

        bookVisit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()='Book a visit']")))
        bookVisit.click()
        
        confirmVisit = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[text()=' Confirm your visit ']")))
        confirmVisit.click()
        # If we reach here, test passed
        current_url = driver.current_url
        send_discord_message(f"✅ Luxmed test passed! Current page URL: {current_url}")
        log_run("PASS", f"URL: {current_url}")
        print("Test passed!")
        with open(FLAG_FILE, "w") as f:
            f.write("Test passed.")
    except Exception as e:
        print(f"Test failed: {e}")
        log_run("FAIL", str(e))
    finally:
        driver.quit()


if __name__ == "__main__":
    test_luxmed()
