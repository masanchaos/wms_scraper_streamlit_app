import streamlit as st
import pandas as pd
import pyperclip
import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException

# =================================================================================
# 核心爬蟲與資料處理邏輯
# =================================================================================

class WmsScraper:
    def __init__(self, url, username, password, status_callback=None):
        self.url = url
        self.username = username
        self.password = password
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    def _login(self, driver):
        self._update_status("  > 正在前往登入頁面...")
        driver.get(self.url)
        account_xpath = "//input[@placeholder='example@jenjan.com.tw']"
        password_xpath = "//input[@type='password']"
        account_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, account_xpath)))
        account_input.click()
        account_input.send_keys(self.username)
        password_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, password_xpath)))
        password_input.click()
        password_input.send_keys(self.password)
        password_input.send_keys(Keys.ENTER)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "app")))
        self._update_status("✅ [成功] 登入完成！")
        self._update_status("  > 等待主頁面穩定...")
        time.sleep(5)

    def _navigate_to_picking_complete(self, driver):
        self._update_status("  > 尋找「揀貨管理」菜單...")
        picking_management_xpath = "//a[.//div[text()='揀貨管理']]"
        # 故意只用 WebDriverWait，讓它在找不到時拋出錯誤，以便被 run() 中的 except 捕捉
        WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()

        self._update_status("  > 點擊「揀包完成」分頁按鈕...")
        picking_complete_tab_xpath = "//div[contains(@class, 'btn') and contains(., '揀包完成')]"
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, picking_complete_tab_xpath))).click()
        self._update_status("✅ [成功] 已進入揀包完成頁面！")
        
    def _scrape_data(self, driver):
        # 這個偵錯版本不會執行到這一步
        pass

    def run(self):
        chrome_options = Options()
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        driver = None
        try:
            self._update_status("  > 正在初始化 WebDriver...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_window_size(1920, 1080)
            
            self._login(driver)
            self._navigate_to_picking_complete(driver) # 預期會在此處失敗
            
            # 如果成功，理論上不會執行到這裡
            self._update_status("✅ [成功] 所有資料抓取完成！")
            return pd.DataFrame() # 返回空 DataFrame
        except Exception as e:
            # 這是偵錯的關鍵：在拋出任何錯誤之前，先印出頁面原始碼
            if driver:
                self._update_status("  > ❗️ 發生錯誤！正在擷取當前頁面 HTML 進行分析...")
                # 將 HTML 原始碼印到 Streamlit 的日誌中
                print("\n" + "="*25 + " DEBUG: PAGE SOURCE ON ERROR " + "="*25)
                print(driver.page_source)
                print("="*70 + "\n")
            # 重新拋出原始錯誤，讓 Streamlit 顯示錯誤訊息
            raise e
        finally:
            if driver:
                driver.quit()

# --- Streamlit UI (保持不變) ---
st.set_page_config(page_title="WMS 資料擷取工具 (偵錯模式)", page_icon="🐞", layout="wide")
st.title("🐞 WMS 網頁資料擷取工具 (偵錯模式)")
st.warning("此為偵錯專用版本，目的是在發生錯誤時獲取頁面 HTML 原始碼。")

with st.sidebar:
    st.header("⚙️ 連結與登入設定")
    url = st.text_input("目標網頁 URL", value="https://wms.jenjan.com.tw/")
    username = st.text_input("帳號", value="jeff02")
    password = st.text_input("密碼", value="j93559091", type="password")

start_button = st.button("🚀 開始執行偵錯", type="primary", use_container_width=True)

if start_button:
    status_area = st.empty()
    def streamlit_callback(message): status_area.info(message)
    with st.spinner("正在執行中，預期會在中途停止並顯示錯誤..."):
        try:
            scraper = WmsScraper(url, username, password, status_callback=streamlit_callback)
            scraper.run()
        except Exception as e:
            status_area.error("❌ 執行時發生預期中的錯誤，請查看下方日誌：")
            st.exception(e)
            st.info("請將上方包含「PAGE SOURCE ON ERROR」的完整日誌複製給我，以進行分析。")
