import streamlit as st
import pandas as pd
import pyperclip
import datetime
import time
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException

# =================================================================================
# 核心爬蟲與資料處理邏輯 (與前一版相同)
# =================================================================================

class WmsScraper:
    # ... 為了節省篇幅，此處省略 WmsScraper class 的完整程式碼 ...
    # ... 請使用您現有的、可成功運作的版本即可 ...
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
        self._update_status("  > 尋找導覽菜單...")
        picking_management_xpath = "//a[@href='/admin/pickup']"
        try:
            picking_management_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, picking_management_xpath))
            )
            picking_management_button.click()
        except Exception as e:
            self._update_status("  > ❗️ 致命錯誤：無法找到或點擊導覽菜單。")
            raise e

        self._update_status("  > 正在等待分頁區塊載入...")
        default_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '未揀訂單') or contains(., 'Unpicked'))]"
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, default_tab_xpath)))
        
        self._update_status("  > 點擊「揀包完成」分頁按鈕...")
        picking_complete_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '揀包完成') or contains(., 'Complete'))]"
        WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, picking_complete_tab_xpath))).click()
        self._update_status("✅ [成功] 已進入揀包完成頁面！")
        
    def _scrape_data(self, driver):
        self._update_status("  > 點擊查詢按鈕以載入資料...")
        query_button_xpath = "//div[contains(@class, 'btn-primary')]"
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, query_button_xpath))).click()
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'list-items')]/div[contains(@class, 'item')]")))
        self._update_status("  > 資料已初步載入。")
        
        all_data = []
        page_count = 1
        while True:
            self._update_status(f"  > 正在抓取第 {page_count} 頁的資料...")
            time.sleep(1.5)
            item_rows_xpath = "//div[contains(@class, 'list-items')]/div[contains(@class, 'item')]"
            rows = driver.find_elements(By.XPATH, item_rows_xpath)
            if not rows: break
            for row in rows:
                shipping_method, tracking_code = "", ""
                try:
                    shipping_method = row.find_element(By.XPATH, "./div[2]/div[3]").text.strip()
                    tracking_code_input = row.find_element(By.XPATH, "./div[2]/div[4]//input")
                    tracking_code = tracking_code_input.get_property('value').strip()
                    if shipping_method or tracking_code:
                        all_data.append({"寄送方式": shipping_method, "主要運送代碼": tracking_code})
                except Exception: continue
            try:
                next_button_xpath = "//button[normalize-space()='下一頁' or normalize-space()='Next']"
                next_button = driver.find_element(By.XPATH, next_button_xpath)
                if next_button.get_attribute('disabled'): break
                else:
                    driver.execute_script("arguments[0].click();", next_button)
                    page_count += 1
                    WebDriverWait(driver, 10).until(EC.staleness_of(rows[0]))
            except Exception: break
        return all_data

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
            self._navigate_to_picking_complete(driver)
            time.sleep(3)
            data = self._scrape_data(driver)
            
            self._update_status("✅ [成功] 所有資料抓取完成！")
            return pd.DataFrame(data)
        finally:
            if driver:
                driver.quit()

# ... generate_report_text 和 process_and_output_data 保持不變...
def generate_report_text(df_to_process, display_timestamp, report_title):
    # ... (省略未變動的程式碼) ...
    pass
def process_and_output_data(df, status_callback):
    # ... (省略未變動的程式碼) ...
    pass


# =================================================================================
# 新增：憑證處理函式
# =================================================================================
CREDENTIALS_FILE = "credentials.json"

def load_credentials():
    """從伺服器上的檔案載入已儲存的帳號密碼"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {} # 如果檔案毀損或找不到，返回空字典
    return {}

def save_credentials(username, password):
    """將帳號密碼儲存到伺服器上的檔案"""
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump({"username": username, "password": password}, f)

def clear_credentials():
    """從伺服器上刪除已儲存的帳號密碼檔案"""
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)


# =================================================================================
# Streamlit 前端介面設計 (已更新)
# =================================================================================

st.set_page_config(page_title="WMS 物流資料擷取工具", page_icon="🚚", layout="wide")

# --- 初始化 Session State ---
if 'scraping_done' not in st.session_state:
    st.session_state.scraping_done = False
if 'final_df' not in st.session_state:
    st.session_state.final_df = pd.DataFrame()
if 'report_texts' not in st.session_state:
    st.session_state.report_texts = {}

# --- 側邊欄：設定區 (已更新) ---
with st.sidebar:
    
    st.header("⚙️ 連結與登入設定")

    # 載入已儲存的憑證
    saved_creds = load_credentials()
    saved_username = saved_creds.get("username", "")
    saved_password = saved_creds.get("password", "")

    url = st.text_input("目標網頁 URL", value="https://wms.jenjan.com.tw/")
    
    # 輸入框的預設值來自載入的憑證
    username = st.text_input("帳號", value=saved_username)
    password = st.text_input("密碼", value=saved_password, type="password")
    
    # 新增「記住我」功能
    remember_me = st.checkbox("記住我 (下次自動填入帳密)")
    
    st.warning("⚠️ **安全性提醒**:\n勾選「記住我」會將帳密以可讀取的形式保存在伺服器上。僅建議在您信任此服務且帳號非高度敏感的情況下使用。")
    

# --- 主頁面：標題與控制區 ---
st.title("🚚 WMS 網頁資料擷取工具")
st.markdown("---")

start_button = st.button("🚀 開始擷取資料", type="primary", use_container_width=True)

if start_button:
    # --- 新增：處理「記住我」的邏輯 ---
    if remember_me:
        save_credentials(username, password)
    else:
        clear_credentials()

    # --- 執行爬蟲 (與之前相同) ---
    st.session_state.scraping_done = False
    status_area = st.empty()

    def streamlit_callback(message):
        status_area.info(message)

    with st.spinner("正在執行中，請勿關閉視窗..."):
        try:
            # 確保使用者有輸入帳密
            if not username or not password:
                status_area.error("❌ 請務必輸入帳號和密碼！")
            else:
                scraper = WmsScraper(url, username, password, status_callback=streamlit_callback)
                result_df = scraper.run()
                
                if not result_df.empty:
                    # (為了節省篇幅，此處省略 process_and_output_data 的呼叫，您現有的版本即可)
                    st.session_state.scraping_done = True
                    status_area.success("🎉 所有任務完成！請查看下方的結果。")
                else:
                    status_area.warning("⚠️ 抓取完成，但沒有收到任何資料。")

        except Exception as e:
            st.session_state.scraping_done = False
            status_area.error(f"❌ 執行時發生致命錯誤：")
            st.exception(e)

# --- 結果顯示區 (與之前相同) ---
if st.session_state.scraping_done:
    st.markdown("---")
    st.header("📊 擷取結果")
    # ... (省略未變動的 UI 程式碼) ...
