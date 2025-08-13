import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
import re
import base64
import io
import html

# 核心函式庫，請確保已安裝 (pip install ...)
import pdfplumber
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# 使用 webdriver-manager 自動下載並管理 chromedriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# =================================================================================
# 自訂複製按鈕
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    """在 Streamlit 中建立一個自訂樣式的 HTML 複製按鈕"""
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
# 核心爬蟲邏輯
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback: self.status_callback(message)

    def _initialize_driver(self):
        """初始化 WebDriver，並自動下載/管理對應的 chromedriver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        # 增加 user-agent 模擬正常瀏覽器
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        settings = {
           "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
           "selectedDestinationId": "Save as PDF",
           "version": 2
        }
        prefs = {
            'printing.print_preview_sticky_settings.appState': json.dumps(settings),
            'savefile.default_directory': '/tmp'
        }
        chrome_options.add_experimental_option('prefs', prefs)
        chrome_options.add_argument('--kiosk-printing')

        self._update_status("  > 初始化 WebDriver (自動下載驅動程式)...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.set_window_size(1920, 1080)
        self._update_status("  > WebDriver 初始化完成。")
        return driver

    # --- WMS Methods ---
    def _login_wms(self, driver, url, username, password):
        self._update_status("  > 正在前往 WMS 登入頁面...")
        driver.get(url)
        account_xpath = "//input[@placeholder='example@jenjan.com.tw']"
        password_xpath = "//input[@type='password']"
        
        # 使用更長的等待時間
        wait = WebDriverWait(driver, 60)
        
        account_input = wait.until(EC.element_to_be_clickable((By.XPATH, account_xpath)))
        account_input.click(); account_input.send_keys(username)
        password_input = wait.until(EC.element_to_be_clickable((By.XPATH, password_xpath)))
        password_input.click(); password_input.send_keys(password)
        password_input.send_keys(Keys.ENTER)
        wait.until(EC.presence_of_element_located((By.ID, "page-container")))
        self._update_status("✅ [成功] WMS 登入完成！")
        time.sleep(3)

    def _navigate_to_picking_complete(self, driver):
        self._update_status("  > 尋找導覽菜單...")
        picking_management_xpath = "//a[@href='/admin/pickup']"
        WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()
        self._update_status("  > 正在等待分頁區塊載入...")
        default_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '未揀訂單') or contains(., 'Unpicked'))]"
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, default_tab_xpath)))
        self._update_status("  > 點擊「揀包完成」分頁按鈕...")
        picking_complete_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '揀包完成') or contains(., 'Complete'))]"
        WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.XPATH, picking_complete_tab_xpath))).click()
        self._update_status("✅ [成功] 已進入揀包完成頁面！")

    def _scrape_data(self, driver):
        self._update_status("  > 點擊查詢按鈕以載入資料...")
        query_button_xpath = "//div[contains(@class, 'btn-primary')]"
        WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.XPATH, query_button_xpath))).click()
        loading_spinner_xpath = "//div[contains(@class, 'j-loading')]"
        WebDriverWait(driver, 60).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
        self._update_status("  > 資料已初步載入。")
        all_data = []
        page_count = 1
        item_list_container_xpath = "//div[contains(@class, 'list-items')]"
        while True:
            self._update_status(f"  > 正在抓取第 {page_count} 頁的資料...")
            current_page_rows = WebDriverWait(driver, 60).until(EC.presence_of_all_elements_located((By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")))
            if not current_page_rows: break
            first_row_text_before_click = current_page_rows[0].text
            for row in current_page_rows:
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
                driver.execute_script("arguments[0].click();", next_button)
                page_count += 1
                timeout = 60; start_time = time.time()
                while True:
                    if time.time() - start_time > timeout: raise TimeoutException(f"頁面內容在{timeout}秒內未刷新。")
                    WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
                    new_first_row = driver.find_element(By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')][1]")
                    if new_first_row.text != first_row_text_before_click:
                        self._update_status(f"  > 第 {page_count} 頁內容已成功刷新。")
                        break
                    time.sleep(0.5)
            except Exception:
                self._update_status(f"  > 未找到下一頁按鈕或翻頁失敗，抓取結束。")
                break
        self._update_status("  > 所有頁面資料抓取完畢。")
        return all_data

    # --- Main Execution Flows ---
    # 【偵錯強化版】
    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_driver()
            # 增加頁面載入超時時間，應對高延遲網路
            driver.set_page_load_timeout(60)
            
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            time.sleep(2)
            data = self._scrape_data(driver)
            return pd.DataFrame(data)
        except Exception as e:
            self._update_status(f"❌ WMS 抓取過程中發生錯誤: {e}")
            
            # 【重要】錯誤時截圖並顯示在 Streamlit 介面上
            if driver:
                try:
                    screenshot_path = "wms_error_screenshot.png"
                    driver.save_screenshot(screenshot_path)
                    self._update_status(f"  > [偵錯] 已儲存錯誤畫面至 {screenshot_path}")
                    st.error("偵測到 WMS 執行錯誤，以下是錯誤發生時的畫面：")
                    st.image(screenshot_path)
                except Exception as screenshot_e:
                    st.warning(f"嘗試儲存錯誤畫面失敗: {screenshot_e}")
            
            return None # 回傳 None 表示失敗
        finally:
            if driver:
                driver.quit()

    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_niceshoppy(driver, url, username, password)
            wait = WebDriverWait(driver, 20)
            
            self._update_status("  > 準備進入「其他用戶」任務頁面...")
            other_users_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "其他用戶")))
            other_users_link.click()
            self._update_status("  > 已進入任務頁面。")

            self._update_status("  > 步驟 1: 正在掃描所有已存在的任務...")
            existing_task_ids = set()
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                task_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in task_links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match:
                                existing_task_ids.add(int(match.group(1)))
                    except StaleElementReferenceException:
                        continue
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height
            max_existing_id = max(existing_task_ids) if existing_task_ids else 0
            self._update_status(f"  > [成功] 掃描完成！當前最大 Task ID 為: {max_existing_id}。")

            self._update_status(f"  > 步驟 2: 正在貼上 {len(codes_to_process)} 筆代碼...")
            text_area = wait.until(EC.visibility_of_element_located((By.NAME, "unimart")))
            text_area.clear()
            codes_as_string = "\n".join(codes_to_process)
            driver.execute_script("arguments[0].value = arguments[1];", text_area, codes_as_string)
            self._update_status("  > 代碼已貼上。")

            self._update_status("  > 步驟 3: 點擊『產出寄件單』按鈕...")
            submit_button_xpath = "//form[@id='shipping-list-submit-form']//a[contains(text(), '產出寄件單')]"
            driver.find_element(By.XPATH, submit_button_xpath).click()
            
            self._update_status(f"  > 步驟 4: 正在等待新任務生成 (ID需大於 {max_existing_id})...")
            long_wait = WebDriverWait(driver, 120)
            def find_new_task_with_scroll(driver):
                links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in reversed(links):
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match:
                                task_id = int(match.group(1))
                                if task_id > max_existing_id:
                                    return task_id
                    except StaleElementReferenceException: continue
                driver.execute_script("window.scrollBy(0, 500);")
                return False
            new_task_id = long_wait.until(find_new_task_with_scroll)
            self._update_status(f"  > [成功] 已偵測到新任務！Task ID: {new_task_id}。")

            self._update_status(f"  > 步驟 5: 正在等待任務 ID {new_task_id} 的列印按鈕變為可用...")
            print_button_xpath = f"//a[@class='btn btn-primary btn-sm' and contains(@href, 'task_id={new_task_id}')]"
            print_wait = WebDriverWait(driver, 300)
            
            latest_button = print_wait.until(EC.presence_of_element_located((By.XPATH, print_button_xpath)))
            self._update_status(f"  > [成功] 按鈕已可用！準備點擊並擷取PDF。")
            
            original_window = driver.current_window_handle
            driver.execute_script("arguments[0].click();", latest_button)
            
            wait.until(EC.number_of_windows_to_be(2))
            for window_handle in driver.window_handles:
                if window_handle != original_window:
                    driver.switch_to.window(window_handle)
                    break
            self._update_status("  > 已切換到列印分頁。")
            time.sleep(5)

            self._update_status("  > 步驟 6: 正在從瀏覽器直接生成 PDF 數據...")
            result = driver.execute_cdp_cmd("Page.printToPDF", {'printBackground': True})
            pdf_content = base64.b64decode(result['data'])
            self._update_status("  > [成功] 已獲取 PDF 數據。")

            self._update_status("  > 步驟 7: 正在解析 PDF 並提取所有物流條碼...")
            full_text = ""
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
            
            extracted_barcodes = re.findall(r'物流條碼：\s*([A-Z0-9]{16})', full_text)
            unique_barcodes = sorted(list(set(extracted_barcodes)))
            
            if not unique_barcodes:
                self._update_status("  > ❗ 警告: 未能在PDF中找到符合格式的物流條碼。")
                
            self._update_status(f"  > [完成] 共提取到 {len(unique_barcodes)} 筆不重複的物流條碼。")
            
            driver.close()
            driver.switch_to.window(original_window)
            return unique_barcodes

        except Exception as e:
            self._update_status(f"  > ❗️ 蝦皮出貨快手處理過程中發生錯誤: {e}")
            try:
                if driver:
                    error_path = 'niceshoppy_fatal_error.png'
                    driver.save_screenshot(error_path)
                    st.error("偵測到 NiceShoppy 執行錯誤，以下是錯誤發生時的畫面：")
                    st.image(error_path)
            except: pass
            return None
        finally:
            if driver: driver.quit()


# =================================================================================
# 資料處理與報告生成
# =================================================================================
def generate_report_text(df_to_process, display_timestamp, report_title):
    if df_to_process.empty:
        summary = f"--- {report_title} ---\n\n指定條件下無資料。"
        full_report = f"擷取時間: {display_timestamp} (台北時間)\n\n{summary}"
        return summary, full_report
    summary_df = df_to_process.groupby('寄送方式', observed=False).size().reset_index(name='數量')
    total_count = len(df_to_process)
    max_len = summary_df['寄送方式'].astype(str).str.len().max() + 2 if not summary_df.empty else 10
    summary_lines = ["==============================", f"=== {report_title} ===", "=============================="]
    for _, row in summary_df.iterrows():
        if row['數量'] > 0:
            method_part = f"{row['寄送方式']}:"; count_part = str(row['數量'])
            line = f"{method_part:<{max_len}} {count_part:>8}"
            summary_lines.append(line)
    summary_lines.append("------------------------------")
    summary_lines.append(f"總計: {total_count}")
    summary_text = "\n".join(summary_lines)
    details_text = df_to_process.to_string(index=False)
    full_report_text = (f"擷取時間: {display_timestamp} (台北時間)\n\n{summary_text}\n\n"
                      "==============================\n======== 資 料 明 細 ========\n==============================\n\n"
                      f"{details_text}")
    return summary_text, full_report_text

def process_and_output_data(df, status_callback):
    status_callback("  > 細分組...")
    df['主要運送代碼'] = df['主要運送代碼'].astype(str)
    condition = (df['寄送方式'] == '7-11') & (df['主要運送代碼'].str.match(r'^\d', na=False))
    df.loc[condition, '寄送方式'] = '711大物流'
    now = datetime.datetime.now(ZoneInfo("Asia/Taipei"))
    display_timestamp = now.strftime("%Y-%m-%d %H:%M")
    priority_order = ['7-11', '711大物流', '全家', '萊爾富', 'OK', '蝦皮店到店', '蝦皮店到家']
    all_methods = df['寄送方式'].unique().tolist()
    final_order = [m for m in priority_order if m in all_methods] + sorted([m for m in all_methods if m not in priority_order])
    df['寄送方式'] = pd.Categorical(df['寄送方式'], categories=final_order, ordered=True)
    df_sorted_all = df.sort_values(by='寄送方式')
    default_methods = ['7-11', '711大物流', '全家', '萊爾富', 'OK', '蝦皮店到店', '蝦皮店到家']
    df_filtered = df_sorted_all[df_sorted_all['寄送方式'].isin(default_methods)]
    st.session_state.df_filtered = df_filtered
    st.session_state.final_df = df_sorted_all
    seven_codes = df_sorted_all[df_sorted_all['寄送方式'] == '7-11']['主要運送代碼'].tolist()
    st.session_state.seven_eleven_codes = [code for code in seven_codes if code]
    st.session_state.report_texts['filtered_summary'], st.session_state.report_texts['filtered_full'] = generate_report_text(df_filtered, display_timestamp, "指定項目分組統計")
    st.session_state.report_texts['all_summary'], st.session_state.report_texts['all_full'] = generate_report_text(df_sorted_all, display_timestamp, "所有項目分組統計")
    st.session_state.file_timestamp = now.strftime("%y%m%d%H%M")
    status_callback("✅ 資料處理完成！")

# =================================================================================
# 憑證管理
# =================================================================================
CREDENTIALS_FILE_WMS = "credentials_wms.json"
CREDENTIALS_FILE_SHOPPY = "credentials_shoppy.json"
def load_credentials(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}
    return {}

def save_credentials(file_path, username, password):
    with open(file_path, 'w') as f: json.dump({"username": username, "password": password}, f)

def clear_credentials(file_path):
    if os.path.exists(file_path): os.remove(file_path)

# =================================================================================
# Streamlit 前端介面
# =================================================================================
st.set_page_config(page_title="WMS & Shoppy 工具", page_icon="🚚", layout="wide")

# 初始化 session_state
if 'wms_scraping_done' not in st.session_state: st.session_state.wms_scraping_done = False
if 'seven_eleven_codes' not in st.session_state: st.session_state.seven_eleven_codes = []
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state: st.session_state.df_filtered = pd.DataFrame()
if 'report_texts' not in st.session_state: st.session_state.report_texts = {}
if 'shoppy_task_done' not in st.session_state: st.session_state.shoppy_task_done = False
if 'extracted_barcodes' not in st.session_state: st.session_state.extracted_barcodes = []

# --- 側邊欄 ---
with st.sidebar:
    st.image("https://www.jenjan.com.tw/images/logo.svg", width=200)
    with st.expander("⚙️ WMS 設定", expanded=True):
        wms_creds = load_credentials(CREDENTIALS_FILE_WMS)
        wms_url = st.text_input("WMS URL", value="https://wms.jenjan.com.tw/", key="wms_url")
        wms_username = st.text_input("WMS 帳號", value=wms_creds.get("username", ""), key="wms_user")
        wms_password = st.text_input("WMS 密碼", value=wms_creds.get("password", ""), type="password", key="wms_pass")
        wms_remember = st.checkbox("記住 WMS 帳密", value=bool(wms_creds), key="wms_rem")
    with st.expander("⚙️ 蝦皮出貨快手設定", expanded=True):
        shoppy_creds = load_credentials(CREDENTIALS_FILE_SHOPPY)
        shoppy_url = st.text_input("快手 URL", value="https://niceshoppy.cc/task/", key="shoppy_url")
        shoppy_username = st.text_input("快手 帳號", value=shoppy_creds.get("username", "service.jenjan@gmail.com"), key="shoppy_user")
        shoppy_password = st.text_input("快手 密碼", value=shoppy_creds.get("password", "jenjan24488261"), type="password", key="shoppy_pass")
        shoppy_remember = st.checkbox("記住 快手 帳密", value=bool(shoppy_creds), key="shoppy_rem")
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在伺服器上。")

st.title("🚚 WMS & 蝦皮出貨快手 自動化工具")
main_tab1, main_tab2 = st.tabs(["📊 WMS 資料擷取", "📦 蝦皮出貨快手"])

# --- WMS 資料擷取分頁 ---
with main_tab1:
    st.header("步驟一：從 WMS 擷取今日資料")
    if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
        if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
        else: clear_credentials(CREDENTIALS_FILE_WMS)
        st.session_state.wms_scraping_done = False
        st.session_state.seven_eleven_codes = []
        st.session_state.shoppy_task_done = False
        st.session_state.extracted_barcodes = []
        progress_text = st.empty()
        
        def streamlit_callback(message):
            progress_text.info(message)

        try:
            if not wms_username or not wms_password:
                st.error("❌ 請務必輸入 WMS 帳號和密碼！")
            else:
                streamlit_callback("準備開始... 🐣")
                tool = AutomationTool(status_callback=streamlit_callback)
                result_df = tool.run_wms_scrape(wms_url, wms_username, wms_password)
                
                if result_df is not None and not result_df.empty:
                    process_and_output_data(result_df, streamlit_callback)
                    st.session_state.wms_scraping_done = True
                    time.sleep(1)
                    progress_text.empty()
                    st.success("🎉 WMS 任務完成！")
                elif result_df is not None and result_df.empty:
                    progress_text.empty()
                    st.warning("⚠️ WMS 抓取完成，但沒有收到任何資料。")
                else: 
                    # 錯誤訊息和截圖會在 run_wms_scrape 函數內部由 st.error 和 st.image 顯示
                    progress_text.empty()

        except Exception as e:
            progress_text.empty()
            st.error(f"❌ 執行 WMS 任務時發生致命錯誤：")
            st.exception(e)

    if st.session_state.get('wms_scraping_done', False):
        st.markdown("---")
        st.header("📊 WMS 擷取結果")
        restab1, restab2 = st.tabs(["📊 指定項目報告", "📋 所有項目報告"])
        with restab1:
            st.subheader("指定項目統計與明細")
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            with col1: create_copy_button(st.session_state.report_texts.get('filtered_full', ''), "一鍵複製報告", key="copy-btn-filtered")
            with col2:
                st.download_button(label="下載 CSV (指定項目)", data=st.session_state.df_filtered.to_csv(index=False, encoding='utf-8-sig'),
                                   file_name=f"picking_data_FILTERED_{st.session_state.file_timestamp}.csv", mime='text/csv', use_container_width=True)
            with col3:
                st.download_button(label="下載 TXT (指定項目)", data=st.session_state.report_texts.get('filtered_full', '').encode('utf-8'),
                                   file_name=f"picking_data_FILTERED_{st.session_state.file_timestamp}.txt", mime='text/plain', use_container_width=True)
            st.text_area("報告內容", value=st.session_state.report_texts.get('filtered_full', '無資料'), height=500, label_visibility="collapsed")
        with restab2:
            st.subheader("所有項目統計與明細")
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            with col1: create_copy_button(st.session_state.report_texts.get('all_full', ''), "一鍵複製報告", key="copy-btn-all")
            with col2:
                st.download_button(label="下載 CSV (所有資料)", data=st.session_state.final_df.to_csv(index=False, encoding='utf-8-sig'),
                                   file_name=f"picking_data_ALL_{st.session_state.file_timestamp}.csv", mime='text/csv', use_container_width=True)
            with col3:
                st.download_button(label="下載 TXT (所有資料)", data=st.session_state.report_texts.get('all_full', '').encode('utf-8'),
                                   file_name=f"picking_data_ALL_{st.session_state.file_timestamp}.txt", mime='text/plain', use_container_width=True)
            st.text_area("報告內容", value=st.session_state.report_texts.get('all_full', '無資料'), height=500, label_visibility="collapsed")

# --- 蝦皮出貨快手分頁 ---
with main_tab2:
    st.header("步驟二：處理蝦皮出貨快手訂單")
    if not st.session_state.get('wms_scraping_done', False):
         st.info("請先在「WMS 資料擷取」分頁中成功擷取資料，才能啟用此功能。")
    elif not st.session_state.get('seven_eleven_codes'):
        st.warning("WMS 資料中未找到需要處理的【純 7-11】運送代碼。")
    else:
        st.success(f"✅ 已從 WMS 系統載入 **{len(st.session_state.seven_eleven_codes)}** 筆 **純 7-11** 的運送代碼。")
        st.text_area("待處理代碼預覽", value="\n".join(st.session_state.seven_eleven_codes), height=150, key="preview_codes")
        
        if st.button("🚀 開始處理並擷取物流條碼", type="primary", use_container_width=True, disabled=not st.session_state.get('seven_eleven_codes')):
            if shoppy_remember: save_credentials(CREDENTIALS_FILE_SHOPPY, shoppy_username, shoppy_password)
            else: clear_credentials(CREDENTIALS_FILE_SHOPPY)
            
            st.session_state.shoppy_task_done = False
            st.session_state.extracted_barcodes = []
            status_area_shoppy = st.empty()
            
            def shoppy_callback(message): 
                status_area_shoppy.info(message)
            
            try:
                if not shoppy_username or not shoppy_password:
                    st.error("❌ 請務必在側邊欄設定中輸入蝦皮出貨快手的帳號和密碼！")
                else:
                    tool = AutomationTool(status_callback=shoppy_callback)
                    result_barcodes = tool.run_niceshoppy_automation(shoppy_url, shoppy_username, shoppy_password, st.session_state.seven_eleven_codes)
                    
                    if result_barcodes is not None:
                        st.session_state.shoppy_task_done = True
                        st.session_state.extracted_barcodes = result_barcodes
                        status_area_shoppy.success(f"🎉 蝦皮出貨快手任務完成！成功擷取 {len(result_barcodes)} 筆物流條碼。")
                    else:
                        st.session_state.shoppy_task_done = False
                        # 錯誤訊息和截圖會在 run_niceshoppy_automation 內部顯示
                        status_area_shoppy.error("❌ 蝦皮出貨快手任務失敗，請查看上方日誌與錯誤畫面。")
            except Exception as e:
                status_area_shoppy.error("❌ 執行蝦皮出貨快手任務時發生致命錯誤：")
                st.exception(e)

    if st.session_state.get('shoppy_task_done', False):
        st.markdown("---")
        st.subheader("✨ 擷取到的物流條碼結果")
        if st.session_state.extracted_barcodes:
            barcodes_text = "\n".join(st.session_state.extracted_barcodes)
            create_copy_button(barcodes_text, f"一鍵複製 {len(st.session_state.extracted_for_codes)} 筆條碼", key="copy-btn-barcodes")
            st.text_area("擷取結果", value=barcodes_text, height=250, label_visibility="collapsed")
        else:
            st.warning("任務執行完畢，但未能從產出的PDF中擷取到任何物流條碼。")
