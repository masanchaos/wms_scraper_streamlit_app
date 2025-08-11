import streamlit as st
import pandas as pd
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =================================================================================
# 偵錯專用爬蟲邏輯
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
        self._update_status("  > [診斷模式] 正在前往登入頁面...")
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
        self._update_status("✅ [診斷模式] 登入成功！")

    def run_diagnostic(self):
        """
        這是一個專為偵錯設計的執行流程。
        它會在嘗試點擊任何東西之前，就先擷取頁面原始碼。
        """
        chrome_options = Options()
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        driver = None
        try:
            self._update_status("  > [診斷模式] 正在初始化 WebDriver...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_window_size(1920, 1080)
            
            # 步驟 1: 登入
            self._login(driver)
            
            # 步驟 2: 穩定後，立刻擷取並印出頁面原始碼
            self._update_status("  > [診斷模式] 登入成功，正在擷取儀表板 HTML 原始碼...")
            time.sleep(5) # 額外等待確保 JS 渲染
            
            # --- 這是本次偵錯的關鍵 ---
            print("\n" + "="*25 + " DEBUG: DASHBOARD PAGE SOURCE " + "="*25)
            print(driver.page_source)
            print("="*70 + "\n")
            # --- -------------------- ---
            
            self._update_status("  > [診斷模式] ✅ HTML 已輸出到日誌。")
            self._update_status("  > [診斷模式] 現在將嘗試尋找導覽按鈕 (此步驟預期會失敗)...")

            # 步驟 3: 執行會導致失敗的步驟，以便程式停止並顯示日誌
            picking_management_xpath = "//a[.//div[text()='揀貨管理']]"
            WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()

        finally:
            if driver:
                driver.quit()

# --- Streamlit UI (保持不變) ---
st.set_page_config(page_title="WMS 資料擷取工具 (診斷模式)", page_icon="🐞", layout="wide")
st.title("🐞 WMS 網頁資料擷取工具 (診斷模式)")
st.warning("此為**最終診斷版本**。請執行並將包含『DASHBOARD PAGE SOURCE』的**完整日誌**回傳。")

with st.sidebar:
    st.header("⚙️ 連結與登入設定")
    url = st.text_input("目標網頁 URL", value="https.://wms.jenjan.com.tw/")
    username = st.text_input("帳號", value="jeff02")
    password = st.text_input("密碼", value="j93559091", type="password")

start_button = st.button("🚀 開始執行最終診斷", type="primary", use_container_width=True)

if start_button:
    status_area = st.empty()
    def streamlit_callback(message): status_area.info(message)
    with st.spinner("正在執行診斷，預期會在中途停止並顯示錯誤..."):
        try:
            scraper = WmsScraper(url, username, password, status_callback=streamlit_callback)
            scraper.run_diagnostic()
        except Exception as e:
            status_area.error("❌ 執行時發生預期中的錯誤，請查看下方日誌：")
            st.exception(e)
            st.success("✅ 診斷完成！請將上方包含「DASHBOARD PAGE SOURCE」的完整日誌複製給我。")
