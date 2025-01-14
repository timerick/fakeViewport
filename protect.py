#!/usr/bin/env python3
import subprocess
import time
import threading
import os
import sys
import getpass
import configparser
import logging
import signal
from logging.handlers import TimedRotatingFileHandler
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from urllib3.exceptions import NewConnectionError
try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    install('webdriver_manager')
    from webdriver_manager.chrome import ChromeDriverManager
config = configparser.ConfigParser()
config.read('config.ini')

# General
SLEEP_TIME = int(config.get('General', 'SLEEP_TIME', fallback=300))
WAIT_TIME = int(config.get('General', 'WAIT_TIME', fallback=30))
MAX_RETRIES = int(config.get('General', 'MAX_RETRIES', fallback=5))
# Validate config variables
if SLEEP_TIME <= 0:
    logging.error("Invalid value for SLEEP_TIME. It should be a positive integer.")
    sys.exit(1)
if WAIT_TIME <= 5:
    logging.error("Invalid value for WAIT_TIME. It should be a positive integer greater than 5.")
    sys.exit(1)
if MAX_RETRIES <= 1:
    logging.error("Invalid value for MAX_RETRIES. It should be a positive integer greater than 1.")
    sys.exit(1)
# Logging
LOG_FILE = config.getboolean('Logging', 'LOG_FILE', fallback=True)
LOG_CONSOLE = config.getboolean('Logging', 'LOG_CONSOLE', fallback=True)
LOGFILE_PATH = config.get('Logging', 'LOG_FILE_PATH', fallback='~')
log_file_path = os.path.join(os.path.expanduser(LOGFILE_PATH), 'protect.log')
# Validate LOGFILE_PATH
if not os.path.isdir(os.path.expanduser(LOGFILE_PATH)):
    logging.error(f"Invalid LOG_FILE_PATH: {LOGFILE_PATH}. The directory does not exist.")
    sys.exit(1)

# Sets Display 0 as the display environment. Very important for selenium to launch chrome.
os.environ['DISPLAY'] = ':0'
# Chrome directory found by navigating to chrome://version/ and copying the Profile Path
user = getpass.getuser()
chrome_data_dir = f"/home/{user}/.config/google-chrome/Default"

# dotenv variables
load_dotenv()
username = os.getenv('MY_USERNAME')
password = os.getenv('MY_PASSWORD')
url = os.getenv('URL')
driver = None # Declare it globally so that it can be accessed in the signal handler function

if not url:
    logging.error("No URL detected. Please make sure you have a .env file in the same directory as this script.")
    sys.exit(1)
logger = logging.getLogger()
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger.setLevel(logging.INFO)
if LOG_FILE:
    #  Define a handler for the file
    file_handler = TimedRotatingFileHandler(log_file_path, when="D", interval=1, backupCount=7)
    file_handler.setLevel(logging.INFO)  # or whatever level you want for the file
    # Set the formatter for the handler
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

if LOG_CONSOLE:
    # Define a handler for the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    # Set the formatter for the handler
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Handles the closing of the script with CTRL+C
def signal_handler(sig, frame):
    global driver
    logging.info('Gracefully shutting down Chrome.')
    if driver is not None:
        driver.quit()
    logging.info("Quitting.")
    sys.exit(0)
# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
# Starts a chrome 'driver' and handles error reattempts
def start_chrome(url):
    retry_count = 0
    max_retries = MAX_RETRIES
    while retry_count < max_retries:
        try:
            chrome_options = Options()
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-translate")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--disable-dev-smh-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument('--ignore-certificate-errors')  # Ignore SSL certificate errors
            chrome_options.add_argument('--ignore-ssl-errors')  # Ignore SSL errors   
            chrome_options.add_argument("--disable-session-crashed-bubble")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument(f"--user-data-dir={chrome_data_dir}")
            chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
            chrome_options.binary_location = "/usr/bin/google-chrome-stable"
            # Add the preference to disable the "Save password" prompt
            chrome_options.add_experimental_option("prefs", {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            })
            webdriver_service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)
            driver.get(url)
            return driver
        except Exception:
            logging.exception(f"An error occurred while starting Chrome: ")
            retry_count += 1
            logging.info(f"Retrying... (Attempt {retry_count} of {max_retries})")
            # If this is the final attempt, kill all existing Chrome processes
            if retry_count == max_retries:
                logging.info("Killing existing Chrome processes...")
                subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # wait for a while before retrying

    logging.info("Failed to start Chrome after maximum retries.")
    logging.info(f"Starting script again in {int(SLEEP_TIME/120)} minutes.")
    time.sleep(SLEEP_TIME/2)
    os.execv(sys.executable, ['python3'] + sys.argv)

# Waits for the fullscreen button to appear, then clicks it.
def click_fullscreen_button(driver):
    try:
        WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.LiveviewControls__Container-sc-6n7ics-0 button.IconButton-pbem09-0'))
        ).click()
        logging.info("Success.")
    except TimeoutException:
        logging.exception("Fullscreen button not found.")
# Waits for the specified title to appear
def wait_for_title(driver, title):
    try:
        WebDriverWait(driver, WAIT_TIME).until(EC.title_contains(title))
        logging.info(f"Loaded {title}")
    except TimeoutException:
        logging.exception(f"Failed to load the {title} page.")
        return False
    return True
# Checks if the live view feed is constantly loading with the three dots and needs a refresh
def check_loading_issue(driver):
    trouble_loading_start_time = None
    for _ in range(30):  # Check every second for 30 seconds
        try:
            trouble_loading = WebDriverWait(driver, 1).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'TimedDotsLoader__Overlay-o4vbzb-0'))
            )
            if trouble_loading:
                if trouble_loading_start_time is None:
                    trouble_loading_start_time = time.time()
                elif time.time() - trouble_loading_start_time >= 15:  # if loading issue persists for 15 seconds
                    logging.info("Video feed trouble persisting for 15 seconds, refreshing the page.")
                    driver.refresh()
                    handle_page(driver)
                    time.sleep(5)
                    return  # Exit the function
        except TimeoutException:
            trouble_loading_start_time = None  # Reset the timer if the issue resolved
        time.sleep(1)
# Checks every 5 minutes if the live view is loaded. Calls the fullscreen function if it is
# If it unloads for any reason and it can't find the live view container, it navigates to the page again
def check_view(driver, url):
    def handle_retry(driver, url, attempt, max_retries):
        logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
        if attempt < max_retries - 1:
            try:
                logging.info("Attempting to load page from url.")
                driver.get(url)
                if handle_page(driver):
                    click_fullscreen_button(driver)
            except Exception as e:
                logging.exception("Error refreshing chrome tab: ")
                logging.error(str(e))
        # Second to last attempt will kill chrome proccess and start new driver
        if attempt == max_retries - 1:
            try:
                logging.info("Killing existing Chrome processes...")
                subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(5)  # wait for a while before retrying
                logging.info("Starting chrome instance...")
                driver = start_chrome(url)
                # Wait for the page to load
                WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
                if handle_page(driver):
                    logging.info("Page successfully reloaded.")
            except Exception as e:
                logging.exception("Error killing chrome: ")
                logging.error(str(e))
        # If last attempt, restart entire script
        elif attempt == max_retries:
            logging.info("Max Attempts reached, restarting script...")
            restart_program(driver)
        return driver

    interval_counter = 0
    retry_count = 0
    max_retries = MAX_RETRIES
    while True:
        try:
            # Wait for the video feeds to load
            video_feeds = WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.liveview__ViewportsWrapper-xf5wrh-2"))
            )
            # Reset count and check loading issue
            retry_count = 0
            # Check if browser is in fullscreen
            screen_size = driver.get_window_size()
            if screen_size['width'] != driver.execute_script("return screen.width;") or \
                screen_size['height'] != driver.execute_script("return screen.height;"):
                logging.info("Making live-view fullscreen.")
                click_fullscreen_button(driver)
            check_loading_issue(driver)
            hide_cursor(driver)
            interval_counter += 1
            if interval_counter % 12 == 0:
                logging.info("Video feeds healthy.")
            time.sleep(SLEEP_TIME)
        except (TimeoutException, NoSuchElementException):
            logging.exception("Video feeds not found or page timed out: ")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except NewConnectionError:
            logging.exception("Connection error occurred: ")
            time.sleep(SLEEP_TIME/2)  # Wait for 2 minutes before retrying
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except Exception as e:
            logging.exception("Unexpected error occurred: ")
            logging.error(str(e))
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
# Waits for the login elements to appear and inputs the username and password
# Only returns true if the page after pressing Return is the Live View
def login(driver):
    try:
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.NAME, 'username'))).send_keys(username)
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.NAME, 'password'))).send_keys(password, Keys.RETURN)
        return wait_for_title(driver, "Live View")
    except TimeoutException:
        logging.exception("Failed to login, elements not found.")
        return False
# Restarts the program with execv to prevent stack overflow
def restart_program(driver):
    logging.info("Gracefully shutting down chrome...")
    driver.quit()
    logging.info(f"Starting script again in {int(SLEEP_TIME/120)} minutes.")
    time.sleep(SLEEP_TIME/2)
    os.execv(sys.executable, ['python3'] + sys.argv)
# Handles whether or not the page loaded directly or got redirected to the login page upon chrome opening
# Restarts program if unexpected results from loggin in, or opening the link.
def handle_page(driver):
    start_time = time.time()  # Capture the starting time
    while True:
        if "Live View" in driver.title:
            logging.info(f"{driver.title} started.")
            time.sleep(3)
            hide_cursor(driver)
            return True
        elif "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
            logging.info("Log-in page found. Inputting credentials...")
            if not login(driver):
                return False
        elif time.time() - start_time > WAIT_TIME:  # If timeout limit is reached
            logging.error("Unexpected page loaded. The page title is: " + driver.title)
            return False
        time.sleep(3)
def hide_cursor(driver):
    # Removes ubiquiti's custom cursor from the page
    driver.execute_script("""
    var styleId = 'hideCursorStyle';
    if (!document.getElementById(styleId)) {
        var style = document.createElement('style');
        style.type = 'text/css';
        style.id = styleId;
        style.innerHTML = '.hMbAUy { cursor: none !important; }';
        document.head.appendChild(style)
        console.log("Custom cursor removed.");
    }
    """)
    # Remove visibility of the player options elements
    driver.execute_script("""
    var styleId = 'hidePlayerOptionsStyle';
    if (!document.getElementById(styleId)) {
        var style = document.createElement('style');
        style.type = 'text/css';
        style.id = styleId;
        style.innerHTML = '.chHzKN { z-index: 0 !important; }';
        document.head.appendChild(style);
        console.log("Player options elements removed.");
    }
    """)
def main():
    logging.info("Starting Fake Viewport v1.5")
    logging.info("Waiting for chrome to load...")
    driver = start_chrome(url)
    # Wait for the page to load
    WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
    if handle_page(driver):
        # Start the check_view function in a separate thread
        logging.info(f"Checking health of page every {int(SLEEP_TIME/60)} minutes...")
        threading.Thread(target=check_view, args=(driver, url)).start()
    else:
        logging.error("Error loading the live view. Restarting the program.")
        restart_program(driver)
if __name__ == "__main__":
    main()