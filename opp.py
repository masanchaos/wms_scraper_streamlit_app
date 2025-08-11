import streamlit as st
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# =================================================================================
# 裸機診斷爬蟲邏輯
# =================================================================================

class WmsScraper:
    def __init__(self, url, status_callback=None):
        self.url = url
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    def run_barebones_diagnostic(self):
        """
        只執行最基本的操作：訪問 URL 並獲取頁面原始碼。
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        
        driver = None
        try:
            self._update_status("  > [裸機診斷] 正在初始化 WebDriver...")
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_window_size(1920, 1080)
            
            self._update_status(f"  > [裸機診斷] 正在前往目標 URL: {self.url}")
            driver.get(self.url)
            
            self._update_status("  > 頁面已請求，等待 10 秒讓其完全載入或失敗...")
            time.sleep(10)
            
            self._update_status("  > 正在擷取登入頁面的 HTML 原始碼...")
            # --- 這是本次診斷的唯一目的 ---
            print("\n" + "="*25 + " DEBUG: LOGIN PAGE SOURCE " + "="*25)
            print(driver.page_source)
            print("="*70 + "\n")
            # --- -------------------- ---
            
            self._update_status("  > ✅ HTML 已成功輸出到日誌。")

        finally:
            if driver:
                driver.quit()

# --- Streamlit UI ---
st.set_page_config(page_title="WMS 裸機診斷", page_icon="🔬", layout="wide")
st.title("🔬 WMS 裸機診斷工具")
st.warning("此版本只會訪問目標 URL 並印出其 HTML 原始碼，用於最終診斷。")
st.info("執行成功後，請前往 'Manage app' 查看日誌。")

with st.sidebar:
    st.header("⚙️ 連結設定")
    url = st.text_input("目標網頁 URL", value="https://wms.jenjan.com.tw/")

start_button = st.button("🚀 開始執行裸機診斷", type="primary", use_container_width=True)

if start_button:
    status_area = st.empty()
    def streamlit_callback(message): status_area.info(message)
    
    with st.spinner("正在執行診斷..."):
        try:
            scraper = WmsScraper(url, status_callback=streamlit_callback)
            scraper.run_barebones_diagnostic()
            status_area.success("✅ 診斷執行完畢！請前往 'Manage app' 查看日誌獲取 HTML 原始碼。")
        except Exception as e:
            status_area.error("❌ 執行時發生了意外的錯誤：")
            st.exception(e)
