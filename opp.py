# =================================================================================
# 匯入所有必要的函式庫
# =================================================================================
import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
import re
import base64
import pdfplumber
import io
import html
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

# Selenium and WebDriver Manager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
# 【修改】不再需要 webdriver_manager
# from webdriver_manager.chrome import ChromeDriverManager

# =================================================================================
# 自訂複製按鈕 (維持不變)
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    # ... (此函數內容維持原樣)
    pass

# =================================================================================
# 核心爬蟲邏輯 (已修改 Driver 初始化方式)
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback: self.status_callback(message)

    # --- 通用的 Driver 初始化函式 (已修改為適用 Streamlit Cloud) ---
    def _initialize_driver(self, for_shoppy=False):
        if for_shoppy:
            self._update_status("  > 初始化蝦皮快手 WebDriver...")
        else:
            self._update_status("  > 初始化 WMS WebDriver...")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        if for_shoppy:
            self._update_status("  > 配置「列印為PDF」功能...")
            settings = {
                "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
                "selectedDestinationId": "Save as PDF",
                "version": 2
            }
            prefs = {'printing.print_preview_sticky_settings.appState': json.dumps(settings)}
            options.add_experimental_option('prefs', prefs)
            options.add_argument('--kiosk-printing')

        # 【核心修改】直接指定在 Streamlit Cloud 上由 packages.txt 安裝的 chromedriver 路徑
        service = Service('/usr/bin/chromedriver')
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    # --- WMS Methods (維持不變，但調用 initialize_driver 的方式改變) ---
    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            # 調用通用的初始化函式
            driver = self._initialize_driver(for_shoppy=False)
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            time.sleep(2)
            data = self._scrape_data(driver)
            return pd.DataFrame(data)
        except Exception as e:
            self._update_status(f"❌ WMS 抓取過程中發生錯誤: {e}")
            return None
        finally:
            if driver: driver.quit()

    # --- NiceShoppy Methods (維持不變，但調用 initialize_driver 的方式改變) ---
    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            # 調用通用的初始化函式，並告知是為了 shoppy
            driver = self._initialize_driver(for_shoppy=True)
            # ... (後續所有蝦皮快手的邏輯完全不變)
            
        except Exception as e:
            self._update_status(f"❌ 蝦皮快手處理過程中發生錯誤: {e}")
            if driver:
                try:
                    error_path = 'shoppy_error.png'
                    driver.save_screenshot(error_path)
                    self._update_status(f"  > 錯誤畫面已截圖至 {error_path}")
                except: pass
            return False
        finally:
            if driver: driver.quit()

    # ... (其他 _login_wms, _scrape_data 等函式維持原樣)

# =================================================================================
# Streamlit UI (維持不變)
# =================================================================================
st.set_page_config(page_title="WMS & Shoppy 工具", page_icon="🚚", layout="wide")
# ... (後續所有 Streamlit 的前端介面程式碼都維持原樣，無需改動)
