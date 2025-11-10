import os
import time
import json
import random
import tempfile
import shutil
import zipfile
import signal
import requests
import psutil
import logging
from typing import Optional, Tuple

from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# =============================================
# RAZORPAY MONITOR - RENDER OPTIMIZED v2.0
# =============================================

# Configure logging for Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Render-specific configuration
if os.environ.get('RENDER'):
    # Render production settings
    HEADLESS_MODE = True
    CHROME_PATH = "/usr/bin/google-chrome"
    CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
    FLASK_HOST = "0.0.0.0"
    FLASK_PORT = int(os.environ.get("PORT", 5500))
    WAIT_SECONDS = 10
else:
    # Local development settings
    HEADLESS_MODE = False
    FLASK_HOST = "0.0.0.0"
    FLASK_PORT = 5500
    WAIT_SECONDS = 6

BOT_TOKEN = os.environ.get('BOT_TOKEN', "YOUR_BOT_TOKEN")
CHAT_ID = os.environ.get('CHAT_ID', "YOUR_CHAT_ID")
PROXY_FILE = "proxy.txt"

app = Flask(__name__)

def load_proxies(filename=PROXY_FILE):
    """Load proxies with Render fallback"""
    if not os.path.exists(filename):
        logger.warning(f"Proxy file {filename} not found, using direct connection")
        return []
    out = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(line)
        logger.info(f"Loaded {len(out)} proxies from {filename}")
    except Exception as e:
        logger.error(f"Error loading proxies: {e}")
    return out

def parse_proxy(proxy_string: str):
    """Parse proxy string with error handling"""
    if not proxy_string:
        return None
    try:
        parts = proxy_string.split(":")
        if len(parts) >= 4:
            return {"host": parts[0], "port": parts[1], "username": parts[2], "password": parts[3]}
        elif len(parts) >= 2:
            return {"host": parts[0], "port": parts[1], "username": None, "password": None}
    except Exception as e:
        logger.error(f"Error parsing proxy {proxy_string}: {e}")
    return None

def create_proxy_auth_extension(proxy_config):
    """Create Chrome proxy extension"""
    ext_dir = tempfile.mkdtemp(prefix="proxy_ext_")
    try:
        manifest = {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "proxy_auth_ext",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"]},
            "minimum_chrome_version": "22.0.0"
        }
        
        manifest_path = os.path.join(ext_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        background_js = f"""
var config = {{
  mode: "fixed_servers",
  rules: {{
    singleProxy: {{
      scheme: "http",
      host: "{proxy_config['host']}",
      port: parseInt({proxy_config['port']})
    }},
    bypassList: ["localhost", "127.0.0.1"]
  }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function(){{}});
function callbackFn(details) {{
  return {{
    authCredentials: {{
      username: "{proxy_config.get('username') or ''}",
      password: "{proxy_config.get('password') or ''}"
    }}
  }};
}}
chrome.webRequest.onAuthRequired.addListener(callbackFn, {{urls: ["<all_urls>"]}}, ['blocking']);
"""
        bg_path = os.path.join(ext_dir, "background.js")
        with open(bg_path, "w", encoding="utf-8") as f:
            f.write(background_js)

        zip_path = os.path.join(tempfile.gettempdir(), f"proxy_ext_{int(time.time()*1000)}.zip")
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.write(manifest_path, "manifest.json")
            z.write(bg_path, "background.js")

        return zip_path
    except Exception as e:
        logger.error(f"Error creating proxy extension: {e}")
        return None
    finally:
        shutil.rmtree(ext_dir, ignore_errors=True)

def kill_existing_chrome():
    """Kill existing Chrome processes"""
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if any(x in name for x in ("chrome", "chromedriver", "chromium")):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(1)
    except Exception as e:
        logger.error(f"Error killing Chrome processes: {e}")

def setup_driver_for_render(proxy_string: Optional[str] = None):
    """Render-optimized driver setup"""
    kill_existing_chrome()
    
    chrome_options = Options()
    
    # Render-specific optimizations
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1200,1000")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    ext_zip = None
    profile_dir = None

    if proxy_string:
        proxy = parse_proxy(proxy_string)
        if proxy and proxy.get("username") and proxy.get("password"):
            ext_zip = create_proxy_auth_extension(proxy)
            if ext_zip:
                chrome_options.add_extension(ext_zip)
        elif proxy:
            chrome_options.add_argument(f"--proxy-server=http://{proxy['host']}:{proxy['port']}")

    profile_dir = tempfile.mkdtemp(prefix="selenium_profile_")
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    try:
        if os.environ.get('RENDER'):
            # Use system Chrome on Render
            chrome_options.binary_location = CHROME_PATH
            service = Service(executable_path=CHROMEDRIVER_PATH)
        else:
            # Local development with webdriver-manager
            service = Service(ChromeDriverManager().install())
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Stealth modifications
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info("Chrome driver started successfully")
        return driver, ext_zip, profile_dir
        
    except Exception as e:
        logger.error(f"Failed to start Chrome driver: {e}")
        # Cleanup on failure
        if ext_zip and os.path.exists(ext_zip):
            try: os.remove(ext_zip) 
            except: pass
        if profile_dir and os.path.exists(profile_dir):
            try: shutil.rmtree(profile_dir, ignore_errors=True) 
            except: pass
        raise e

def send_photo_to_telegram(photo_path, caption=None):
    """Send screenshot to Telegram"""
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        return False, "Bot token not configured"
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption or ""}
            resp = requests.post(url, data=data, files=files, timeout=60)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)

def extract_payment_id(url: str):
    """Extract payment ID from URL"""
    try:
        if "/payments/" in url:
            after = url.split("/payments/", 1)[1]
            pid = after.split("/")[0]
            return pid
    except Exception:
        pass
    return None

SUCCESS_KEYWORDS = [
    "payment successful", "your payment has been completed", "payment authorised",
    "payment authorized", "payment captured", "payment captured successfully", "razorpay_signature"
]

FAILURE_KEYWORDS = [
    "payment failed", "your transaction was failed", "payment declined",
    "transaction failed", "authorization failed", "failed to capture"
]

def check_html_for_keywords(driver):
    """Check page content for payment status keywords"""
    try:
        html_content = driver.page_source or ""
        body_text = ""
        try:
            body_el = driver.find_element("tag name", "body")
            body_text = body_el.text or ""
        except Exception:
            pass
        
        combined_text = (html_content + " " + body_text).lower()

        if "razorpay_signature" in combined_text:
            return "success"
        for s in SUCCESS_KEYWORDS:
            if s in combined_text:
                return "success"
        for f in FAILURE_KEYWORDS:
            if f in combined_text:
                return "failure"
        return None
    except Exception as e:
        logger.error(f"Error checking keywords: {e}")
        return None

def check_url_and_capture(input_url: str):
    """Main monitoring function"""
    proxies = load_proxies()
    proxy_string = random.choice(proxies) if proxies else None
    
    driver = None
    ext_zip = None
    profile_dir = None
    screenshot_path = None
    
    try:
        driver, ext_zip, profile_dir = setup_driver_for_render(proxy_string)
        driver.set_page_load_timeout(WAIT_SECONDS + 10)
        
        try:
            driver.get(input_url)
        except Exception as e:
            logger.warning(f"Page load timeout: {e}")

        start = time.time()
        initial_url = driver.current_url or input_url
        initial_pid = extract_payment_id(initial_url)
        last_url = initial_url
        
        while True:
            elapsed = time.time() - start
            try:
                current_url = driver.current_url or ""
            except Exception:
                current_url = last_url
            
            keyword_result = check_html_for_keywords(driver)
            
            if keyword_result == "success":
                # Capture success screenshot
                try:
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_success_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                    send_photo_to_telegram(screenshot_path, f"✅ Payment Success: {current_url}")
                except Exception as e:
                    logger.error(f"Error capturing success: {e}")

                return {
                    "3ds": True,
                    "status": "Approved",
                    "message": "Payment Captured Successfully ✅",
                    "url": current_url
                }

            if keyword_result == "failure":
                # Capture failure screenshot
                try:
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_failure_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                    send_photo_to_telegram(screenshot_path, f"❌ Payment Failed: {current_url}")
                except Exception as e:
                    logger.error(f"Error capturing failure: {e}")

                return {
                    "3ds": False,
                    "status": "Declined", 
                    "message": "Payment Failed / Declined",
                    "url": current_url
                }

            # Check for URL changes (3DS detection)
            if current_url and current_url != last_url:
                in_pid = extract_payment_id(input_url)
                cur_pid = extract_payment_id(current_url)
                
                if in_pid and cur_pid:
                    norm_in = in_pid.replace("pay_", "")
                    norm_cur = cur_pid.replace("pay_", "")
                    
                    if norm_in != norm_cur:
                        return {
                            "3ds": True,
                            "status": "3DS Required",
                            "message": "3DS Authentication Detected ✅",
                            "url": current_url
                        }

            if elapsed >= WAIT_SECONDS:
                return {
                    "3ds": False,
                    "status": "Timeout",
                    "message": "No activity detected within timeout",
                    "url": current_url
                }

            last_url = current_url
            time.sleep(1)

    except Exception as e:
        logger.error(f"Monitoring error: {e}")
        return {
            "success": False, 
            "3ds": False, 
            "status": "Error", 
            "message": str(e)
        }
    finally:
        # Cleanup resources
        try:
            if driver:
                driver.quit()
        except Exception as e:
            logger.error(f"Error quitting driver: {e}")
        
        try:
            if ext_zip and os.path.exists(ext_zip):
                os.remove(ext_zip)
        except Exception:
            pass
            
        try:
            if profile_dir and os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass
            
        try:
            if screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)
        except Exception:
            pass

@app.route("/")
def home():
    return jsonify({
        "status": "active",
        "service": "Razorpay Monitor",
        "endpoints": {
            "health": "/health",
            "check": "/check?url=YOUR_RAZORPAY_URL"
        }
    })

@app.route("/health")
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route("/check", methods=["GET"])
def check_route():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing ?url parameter"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL format"}), 400

    logger.info(f"Checking URL: {url}")
    result = check_url_and_capture(url)
    return jsonify(result), 200

def handle_signal(sig, frame):
    logger.info(f"Received signal {sig}, shutting down gracefully.")
    os._exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

if __name__ == "__main__":
    logger.info(f"Starting Razorpay Monitor on {FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
