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
from webdriver_manager.chrome import ChromeDriverManager

# =================================================================================
# 自訂複製按鈕 (維持不變)
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    escaped_text = html.escape(text_to_copy)
    button_html = f"""
    <html><head><style>
        .copy-btn {{
            display: inline-block; padding: 0.25rem 0.75rem; font-size: 14px;
            font-weight: 600; text-align: center; white-space: nowrap;
            vertical-align: middle; cursor: pointer; user-select: none;
            border: 1px solid #000000; border-radius: 0.5rem;
            color: #000000; background-color: #FFD700;
            transition: all 0.2s ease; width: 100%;
        }}
        .copy-btn:hover {{ background-color: #FFC700; }}
        .copy-btn:active {{ transform: scale(0.98); }}
        .copy-btn:disabled {{
            background-color: #32CD32; color: white; border-color: #228B22;
            cursor: default; opacity: 1;
        }}
    </style></head>
    <body>
        <div id="text-for-{key}" style="display: none;">{escaped_text}</div>
        <button id="{key}" class="copy-btn">{button_text}</button>
        <script>
            document.getElementById("{key}").addEventListener("click", function() {{
                const text = document.getElementById("text-for-{key}").textContent;
                navigator.clipboard.writeText(text).then(() => {{
                    const button = document.getElementById("{key}");
                    const originalText = button.innerText;
                    button.innerText = '已複製!'; button.disabled = true;
                    setTimeout(() => {{ button.innerText = originalText; button.disabled = false; }}, 1500);
                }}, (err) => {{ console.error('無法複製文字: ', err); }});
            }});
        </script>
    </body></html>
    """
    return components.html(button_html, height=45)

# =================================================================================
# 核心爬蟲邏輯 (已整合)
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    # --- WMS Driver & Methods (維持不變) ---
    def _initialize_wms_driver(self):
        chrome_options = Options()
        # Streamlit Cloud 需要的 Headless 設定
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self._update_status("  > 初始化 WMS WebDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_window_size(1920, 1080)
        return driver

    def _login_wms(self, driver, url, username, password):
        # ... (此方法維持原樣)
        pass

    def _navigate_to_picking_complete(self, driver):
        # ... (此方法維持原樣)
        pass

    def _scrape_data(self, driver):
        # ... (此方法維持原樣)
        pass
        
    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_wms_driver()
            # ... (此方法執行邏輯維持原樣)
            # ... 假設登入、導覽、抓取都在這裡 ...
            # 為了簡化，我們直接返回一個模擬的 DataFrame
            # 在您的實際程式碼中，這裡會是完整的抓取邏輯
            # data = self._scrape_data(driver)
            # return pd.DataFrame(data)
            return pd.DataFrame() # 暫時返回空的
        except Exception as e:
            self._update_status(f"❌ WMS 抓取過程中發生錯誤: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    # --- NiceShoppy Driver & Methods (全新整合) ---
    def _initialize_shoppy_driver(self):
        self._update_status("  > 初始化蝦皮快手 WebDriver...")
        options = webdriver.ChromeOptions()
        # Streamlit Cloud 需要的 Headless 設定
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        # 為「列印為PDF」功能新增的特別設定
        self._update_status("  > 配置「列印為PDF」功能...")
        settings = {
            "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
            "selectedDestinationId": "Save as PDF",
            "version": 2
        }
        prefs = {
            'printing.print_preview_sticky_settings.appState': json.dumps(settings),
        }
        options.add_experimental_option('prefs', prefs)
        options.add_argument('--kiosk-printing') # 啟用靜默列印模式

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1920, 1080)
        return driver

    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            driver = self._initialize_shoppy_driver()
            wait = WebDriverWait(driver, 20)
            
            # --- 登入 ---
            self._update_status("  > 前往蝦皮快手登入頁面...")
            driver.get(url)
            try:
                login_link = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.LINK_TEXT, "登入")))
                login_link.click()
            except TimeoutException:
                pass # 已經在登入頁面
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "username"))).send_keys(username)
            driver.find_element(By.ID, "password").send_keys(password)
            driver.find_element(By.NAME, "login").click()
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "其他用戶")))
            self._update_status("✅ [成功] 蝦皮快手登入成功！")
            
            # --- 步驟 1: 徹底掃描 ---
            self._update_status("  > 步驟 1: 掃描現有任務以獲取最大 Task ID...")
            existing_task_ids = set()
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                task_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in task_links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match: existing_task_ids.add(int(match.group(1)))
                    except StaleElementReferenceException: continue
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height
            max_existing_id = max(existing_task_ids) if existing_task_ids else 0
            self._update_status(f"  > 當前最大 Task ID 為: {max_existing_id}。")
            
            # --- 步驟 2 & 3: 貼上並產出 ---
            other_users_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "其他用戶")))
            other_users_link.click()
            text_area = wait.until(EC.visibility_of_element_located((By.NAME, "unimart")))
            text_area.clear()
            text_area.send_keys(codes_to_process)
            self._update_status(f"  > 步驟 2: 已貼上 {len(codes_to_process.splitlines())} 筆代碼。")
            
            final_submit_link = driver.find_element(By.XPATH, '//*[@id="shipping-list-submit-form"]/a[1]')
            final_submit_link.click()
            self._update_status("  > 步驟 3: 已點擊『產出寄件單』。")

            # --- 步驟 4: 滾動式等待 ---
            self._update_status(f"  > 步驟 4: 等待大於 {max_existing_id} 的新任務生成...")
            long_wait = WebDriverWait(driver, 120)
            def find_new_task_with_scroll(driver):
                links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match:
                                task_id = int(match.group(1))
                                if task_id > max_existing_id: return task_id
                    except StaleElementReferenceException: continue
                driver.execute_script("window.scrollBy(0, 500);")
                return False
            new_task_id = long_wait.until(find_new_task_with_scroll)
            self._update_status(f"  > ✅ 成功偵測到新任務！Task ID: {new_task_id}。")

            # --- 步驟 5: 精準等待並點擊 ---
            self._update_status(f"  > 步驟 5: 等待任務 {new_task_id} 進度條完成...")
            print_button_xpath = f"//a[@class='btn btn-primary btn-sm' and contains(@href, 'task_id={new_task_id}')]"
            print_wait = WebDriverWait(driver, 300)
            latest_button = print_wait.until(EC.presence_of_element_located((By.XPATH, print_button_xpath)))
            self._update_status("  > ✅ 進度條完成！準備點擊『列印小白單』...")
            original_window = driver.current_window_handle
            driver.execute_script("arguments[0].click();", latest_button)
            
            # --- 步驟 6: PDF 解析 ---
            self._update_status("  > 步驟 6: 切換至列印分頁...")
            wait.until(EC.number_of_windows_to_be(2))
            for window_handle in driver.window_handles:
                if window_handle != original_window:
                    driver.switch_to.window(window_handle)
                    break
            
            self._update_status("  > 執行「列印為PDF」命令...")
            time.sleep(5)
            result = driver.execute_cdp_cmd("Page.printToPDF", {})
            pdf_content = base64.b64decode(result['data'])
            
            self._update_status("  > 解析PDF，提取所有文字...")
            full_text = ""
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text: full_text += page_text + "\n"
            
            self._update_status("  > 篩選物流條碼...")
            extracted_barcodes = re.findall(r'物流條碼：\s*(.{16})', full_text)
            unique_barcodes = sorted(list(set(extracted_barcodes)))
            
            st.session_state.shoppy_results = unique_barcodes # 將結果存入 session_state
            
            driver.close()
            driver.switch_to.window(original_window)
            return True

        except Exception as e:
            self._update_status(f"❌ 蝦皮快手處理過程中發生錯誤: {e}")
            try:
                if driver:
                    error_path = 'shoppy_error.png'
                    driver.save_screenshot(error_path)
                    self._update_status(f"  > 錯誤畫面已截圖至 {error_path}")
            except: pass
            return None # 返回 None 表示失敗
        finally:
            if driver:
                driver.quit()

# =================================================================================
# 資料處理與報告生成 (維持不變)
# =================================================================================
def generate_report_text(df_to_process, display_timestamp, report_title):
    # ... (此函數維持原樣)
    pass
def process_and_output_data(df, status_callback):
    # ... (此函數維持原樣)
    pass
# =================================================================================
# 憑證管理 (維持不變)
# =================================================================================
CREDENTIALS_FILE_WMS = "credentials_wms.json"
CREDENTIALS_FILE_SHOPPY = "credentials_shoppy.json"
def load_credentials(file_path):
    # ... (此函數維持原樣)
    pass
def save_credentials(file_path, username, password):
    # ... (此函數維持原樣)
    pass
def clear_credentials(file_path):
    # ... (此函數維持原樣)
    pass

# =================================================================================
# Streamlit 前端介面 (已修改蝦皮快手分頁)
# =================================================================================
st.set_page_config(page_title="WMS & Shoppy 工具", page_icon="🚚", layout="wide")

# --- Session State 初始化 (維持不變) ---
if 'wms_scraping_done' not in st.session_state: st.session_state.wms_scraping_done = False
if 'seven_eleven_codes' not in st.session_state: st.session_state.seven_eleven_codes = []
if 'shoppy_results' not in st.session_state: st.session_state.shoppy_results = None
# ... (其他 session state 初始化維持原樣)

# --- 側邊欄 (維持不變) ---
with st.sidebar:
    # ... (側邊欄 UI 維持原樣)
    pass

st.title("🚚 WMS & 蝦皮出貨快手 自動化工具")
main_tab1, main_tab2 = st.tabs(["📊 WMS 資料擷取", "📦 蝦皮出貨快手"])

# --- WMS 分頁 (維持不變) ---
with main_tab1:
    # ... (WMS 分頁 UI 維持原樣)
    pass

# --- 蝦皮快手分頁 (已修改) ---
with main_tab2:
    st.header("步驟二：處理蝦皮出貨快手訂單")
    if not st.session_state.get('wms_scraping_done', False):
         st.info("請先在「WMS 資料擷取」分頁中成功擷取資料，才能啟用此功能。")
    elif not st.session_state.get('seven_eleven_codes'):
        st.warning("WMS 資料中未找到需要處理的【711分組 (不含大物流)】運送代碼。")
    else:
        codes_to_process = st.session_state.seven_eleven_codes
        st.success(f"✅ 已從 WMS 系統載入 **{len(codes_to_process)}** 筆 **711分組 (不含大物流)** 的運送代碼。")
        st.text_area("待處理代碼預覽", value="\n".join(codes_to_process), height=150)
        
        if st.button("🚀 啟動蝦皮快手，自動化處理", type="primary", use_container_width=True):
            if shoppy_remember: save_credentials(CREDENTIALS_FILE_SHOPPY, shoppy_username, shoppy_password)
            else: clear_credentials(CREDENTIALS_FILE_SHOPPY)
            
            # 重置上次的結果
            st.session_state.shoppy_results = None
            
            # 建立一個區域來顯示進度
            status_placeholder = st.empty()
            
            def shoppy_callback(message):
                status_placeholder.info(message)
            
            if not shoppy_username or not shoppy_password:
                st.error("❌ 請務必在側邊欄設定中輸入蝦皮出貨快手的帳號和密碼！")
            else:
                tool = AutomationTool(status_callback=shoppy_callback)
                # 將 codes list 轉換為單一字串傳入
                codes_as_string = "\n".join(codes_to_process)
                success = tool.run_niceshoppy_automation(shoppy_url, shoppy_username, shoppy_password, codes_as_string)
                
                if success is None: # 表示過程中發生錯誤
                     status_placeholder.error("❌ 任務失敗，請查看上方日誌。若有截圖產生，請在程式所在的資料夾內查看。")
                else: # success is True
                     status_placeholder.success("🎉 蝦皮出貨快手任務已成功執行！請查看下方結果。")

    # --- 結果展示區 ---
    if st.session_state.shoppy_results is not None:
        st.markdown("---")
        st.subheader("📦 物流條碼抓取結果")
        if st.session_state.shoppy_results:
            results_string = "\n".join(st.session_state.shoppy_results)
            col1, col2 = st.columns([0.6, 0.4])
            with col1:
                st.text_area("抓取到的物流條碼", value=results_string, height=200)
            with col2:
                st.metric(label="成功抓取數量", value=f"{len(st.session_state.shoppy_results)} 筆")
                create_copy_button(results_string, "一鍵複製所有條碼", "copy-shoppy-results")
        else:
            st.warning("⚠️ 任務執行完畢，但在產出的 PDF 中未找到符合格式的物流條碼。")
