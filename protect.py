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
LOGFILE_PATH = config.get('Loggig', 'LOG_FILE_PATH', fallback='~')
log_file_path = os.path.join(os.path.expanduser(LOGFILE_PATH), 'protect.log')
# Validate LOGFILE_PATH
if not os.path.isdir(os.path.expanduser(LOGFILE_PATH)):
    logging.error(f"Invalid LOG_FILE_PATH: {LOGFILE_PATH}. The directory does not exist.")
    sys.exit(1)
# API
API = config.getboolean('API', 'USE_API', fallback=False)
API_PATH = config.get('API', 'API_FILE_PATH', fallback='~')
# Validate API_PATH
if not os.path.isdir(os.path.expanduser(API_PATH)):
    logging.error(f"Invalid API_PATH: {API_PATH}. The directory does not exist.")
    sys.exit(1)
# Sets Display 0 as the display environment. Very important for selenium to launch chrome.
os.environ['DISPLAY'] = ':0'
# Chrome directory found by navigating to chrome://version/ and copying the Profile Path
user = getpass.getuser()
chrome_data_dir = f"/home/{user}/.config/google-chrome/Default"

# dotenv variables
load_dotenv()
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
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

if API:
    # get the directory of the current script
    current_dir = os.path.dirname(os.path.realpath(__file__))
    # Construct the path to the file in the user's home directory
    script_start_time_file = os.path.join(os.path.expanduser(API_PATH), 'script_start_time.txt')
    with open(script_start_time_file, 'w') as f:
        f.write(str(datetime.now()))

# Check if the API is already running, start it otherwise
def check_python_script():
    logging.info("Checking if API script is already running...")
    result = subprocess.run(['pgrep', '-f', 'api.py'], stdout=subprocess.PIPE)
    if result.stdout:
        logging.info("API already running.")
    else:
        logging.info("Starting API...")
        # construct the path to api.py
        api_script = os.path.join(current_dir, 'api.py')
        subprocess.Popen(['python3', api_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
            chrome_options.add_argument("-–disable-session-crashed-bubble")
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

    logging.info("Failed to start Chrome after maximum retries. Exiting...")
    sys.exit(1)  # exit with error code

# Waits for the fullscreen button to appear, then clicks it.
def click_fullscreen_button(driver):
    try:
        WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.LiveviewControls__Container-sc-6n7ics-0.ihZxIP button.button__jTNy2Cxe'))
        ).click()
        logging.info("Live view is in fullscreen.")
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
                    time.sleep(5)
                    return  # Exit the function
        except TimeoutException:
            trouble_loading_start_time = None  # Reset the timer if the issue resolved
        time.sleep(1)
# Checks every 5 minutes if the live view is loaded. Calls the fullscreen function if it is
# If it unloads for any reason and it can't find the live view container, it navigates to the page again
def check_view(driver, url):
    if API:
        # Construct the path to the file in the user's home directory
        view_status_file = os.path.join(os.path.expanduser(API_PATH), 'view_status.txt')

    def handle_retry(driver, url, attempt, max_retries):
        logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
        if attempt == max_retries - 1:
            logging.info("Refreshing page...")
            driver.refresh()
            time.sleep(10) # Wait for page to refresh before retrying
        elif attempt == max_retries:
            logging.info("Killing existing Chrome processes...")
            subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # wait for a while before retrying
            logging.info("Starting chrome instance...")
            driver = start_chrome(url)
            # Wait for the page to load
            WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
            if handle_page(driver):
                logging.info("Page successfully reloaded.")
        return driver

    retry_count = 0
    max_retries = MAX_RETRIES
    while True:
        try:
            # Wait for the video feeds to load
            video_feeds = WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.liveview__ViewportsWrapper-xf5wrh-2"))
            )
            if API:
                with open(view_status_file, 'w') as f:
                    f.write('True') #api
            logging.info("Video feeds are present.")
            # Reset count and check loading issue
            retry_count = 0
            # Check if browser is in fullscreen
            screen_size = driver.get_window_size()
            if screen_size['width'] != driver.execute_script("return screen.width;") or \
               screen_size['height'] != driver.execute_script("return screen.height;"):
                logging.info("Browser is not in fullscreen, making it fullscreen.")
                click_fullscreen_button(driver)
            check_loading_issue(driver)
            time.sleep(SLEEP_TIME)
        except (TimeoutException, NoSuchElementException):
            logging.exception(f"Video feeds not found or other error occurred: ")
            time.sleep(WAIT_TIME)
            logging.info("Refreshing chrome tab...")
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            try:
                logging.info("Attempting to load page from url.")
                driver.get(url)
                wait_for_title(driver, "Live View")
                click_fullscreen_button(driver)
                if API:
                    with open(view_status_file, 'w') as f:
                        f.write('True')
            except TimeoutException:
                logging.exception(f"Error refreshing chrome tab: ")
                if API:
                    with open(view_status_file, 'w') as f:
                        f.write('False')
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
    logging.info("Starting script again.")
    os.execv(sys.executable, ['python3'] + sys.argv)
# Handles whether or not the page loaded directly or got redirected to the login page upon chrome opening
# Restarts program if unexpected results from loggin in, or opening the link.
def handle_page(driver):
    start_time = time.time()  # Capture the starting time
    while True:
        if "Live View" in driver.title:
            logging.info(f"{driver.title} started.")
            return True
        elif "Ubiquiti Account" in driver.title:
            logging.info("Log-in page found. Inputting credentials...")
            if not login(driver):
                restart_program(driver)
        elif time.time() - start_time > WAIT_TIME:  # If timeout limit is reached
            logging.error("Unexpected page loaded. The page title is: " + driver.title)
            return False
        time.sleep(3)
def hide_cursor(driver):
    logging.info("Removing custom cursor from page.")
    # Removes ubiquiti's custom cursor from the page
    driver.execute_script("""
    var style = document.createElement('style');
    style.type = 'text/css';
    style.innerHTML = '.hMbAUy { cursor: none !important; }';
    document.head.appendChild(style);
    """)
    logging.info("Removing visibility of player options elements.")
    # Remove visibility of the player options elements
    driver.execute_script("""
    var style = document.createElement('style');
    style.type = 'text/css';
    style.innerHTML = '.chHzKN { z-index: 0 !important; }';
    document.head.appendChild(style);
    """)
def main():
    logging.info("Starting Fake Viewport v1.4")
    if API:
        check_python_script()
    logging.info("Waiting for chrome to load...")
    driver = start_chrome(url)
    # Wait for the page to load
    WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
    logging.info("Chrome loaded.")
    if handle_page(driver):
        hide_cursor(driver)
        # Start the check_view function in a separate thread
        logging.info(f"Started check_view thread. Checking health of page every {int(SLEEP_TIME/60)} minutes...")
        threading.Thread(target=check_view, args=(driver, url)).start()
    else:
        logging.error("Restarting the program...")
        restart_program(driver)
if __name__ == "__main__":
    main()
