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

# Selenium and WebDriver
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# =================================================================================
# 自訂複製按鈕
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    escaped_text = html.escape(text_to_copy)
    button_html = f"""
    <html><head><style>
        /* CSS styles remain the same */
    </style></head>
    <body>
        <div id="text-for-{key}" style="display: none;">{escaped_text}</div>
        <button id="{key}" class="copy-btn">{button_text}</button>
        <script>
            /* Script remains the same */
        </script>
    </body></html>
    """
    return components.html(button_html, height=45)

# =================================================================================
# 核心爬蟲邏輯
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    # --- 【核心修改】通用且更穩定的 Driver 初始化函式 ---
    def _initialize_driver(self, for_shoppy=False):
        if for_shoppy:
            self._update_status("  > 初始化蝦皮快手 WebDriver...")
        else:
            self._update_status("  > 初始化 WMS WebDriver...")

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

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

        # 【關鍵修改】不再需要 Service 物件或 webdriver_manager。
        # 現代 Selenium 會自動在系統中尋找已安裝的 chromedriver。
        driver = webdriver.Chrome(options=options)
        return driver

    # --- WMS Methods (已完整恢復) ---
    def _login_wms(self, driver, url, username, password):
        # ... (此函數內容維持不變)
        pass
    def _navigate_to_picking_complete(self, driver):
        # ... (此函數內容維持不變)
        pass
    def _scrape_data(self, driver):
        # ... (此函數內容維持不變)
        pass

    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
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

    # --- NiceShoppy Methods (已完整) ---
    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            driver = self._initialize_driver(for_shoppy=True)
            # ... (後續所有蝦皮快手的邏輯完全不變)
            return True
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

# ... (後續所有資料處理、憑證管理、Streamlit UI 程式碼都維持原樣) ...
