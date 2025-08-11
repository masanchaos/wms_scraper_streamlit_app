import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components
import html
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException

# =================================================================================
# 自訂複製按鈕
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
# 核心爬蟲邏輯 (已擴充)
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback
    def _update_status(self, message):
        if self.status_callback: self.status_callback(message)
    def _initialize_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self._update_status("  > 初始化 WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_window_size(1920, 1080)
        return driver

    # --- WMS Methods ---
    def _login_wms(self, driver, url, username, password):
        self._update_status("  > 正在前往 WMS 登入頁面...")
        driver.get(url)
        account_xpath = "//input[@placeholder='example@jenjan.com.tw']"
        password_xpath = "//input[@type='password']"
        account_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, account_xpath)))
        account_input.click(); account_input.send_keys(username)
        password_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, password_xpath)))
        password_input.click(); password_input.send_keys(password)
        password_input.send_keys(Keys.ENTER)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "page-container")))
        self._update_status("✅ [成功] WMS 登入完成！")
        time.sleep(3)
    def _navigate_to_picking_complete(self, driver):
        self._update_status("  > 尋找導覽菜單...")
        picking_management_xpath = "//a[@href='/admin/pickup']"
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()
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
        loading_spinner_xpath = "//div[contains(@class, 'j-loading')]"
        WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
        self._update_status("  > 資料已初步載入。")
        all_data = []
        page_count = 1
        item_list_container_xpath = "//div[contains(@class, 'list-items')]"
        while True:
            self._update_status(f"  > 正在抓取第 {page_count} 頁的資料...")
            current_page_rows = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")))
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
                timeout = 20; start_time = time.time()
                while True:
                    if time.time() - start_time > timeout: raise TimeoutException(f"頁面內容在{timeout}秒內未刷新。")
                    WebDriverWait(driver, timeout).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
                    new_first_row = driver.find_element(By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')][1]")
                    if new_first_row.text != first_row_text_before_click:
                        self._update_status(f"  > 第 {page_count} 頁內容已成功刷新。")
                        break
                    time.sleep(0.5)
            except Exception as e:
                self._update_status(f"  > 未找到下一頁按鈕或翻頁失敗 ({e})，抓取結束。")
                break
        self._update_status("  > 所有頁面資料抓取完畢。")
        return all_data

    # --- NiceShoppy Methods ---
    def _login_niceshoppy(self, driver, url, username, password):
        self._update_status("  > 正在前往蝦皮出貨快手頁面...")
        driver.get(url)
        try:
            login_link_xpath = "//a[normalize-space()='登入']"
            login_link = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, login_link_xpath)))
            self._update_status("  > 偵測到尚未登入，點擊「登入」連結...")
            login_link.click()
        except TimeoutException:
            self._update_status("  > 未找到「登入」連結，假設已在登入頁面。")
        self._update_status("  > 正在輸入帳號密碼...")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.NAME, "username"))).send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//h1[contains(text(), '建立超商寄件單')]")))
        self._update_status("✅ [成功] 蝦皮出貨快手登入成功！")

    # --- Main Execution Flows ---
    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            time.sleep(2)
            data = self._scrape_data(driver)
            return pd.DataFrame(data)
        finally:
            if driver: driver.quit()

    # =========================================================================
    # START: DEBUG-ENHANCED NiceShoppy Automation Function
    # =========================================================================
    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_niceshoppy(driver, url, username, password)
            self._update_status("  > 登入成功，準備點擊「其他用戶」標籤...")
            time.sleep(3) 

            wait = WebDriverWait(driver, 20)

            # --- 診斷步驟 1: 檢查是否存在 Iframe ---
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            self._update_status(f"  > [除錯資訊] 頁面中共找到 {len(iframes)} 個 iframe。")
            if len(iframes) > 0:
                self._update_status("  > [除錯資訊] 警告：頁面中存在 iframe，這可能是點擊失敗的原因。")

            # --- 診斷步驟 2: 使用更精確的 XPath 並檢查元素狀態 ---
            # 根據您提供的HTML截圖，按鈕位於 <div class="my-tab"> 內部
            other_user_tab_xpath = "//div[@class='my-tab']//a[normalize-space()='其他用戶']"
            self._update_status("  > [除錯資訊] 使用更精確的 XPath 尋找元素...")

            try:
                other_user_tab = wait.until(EC.presence_of_element_located((By.XPATH, other_user_tab_xpath)))
                self._update_status("  > [除錯資訊] 成功找到元素！")
                # 回報元素狀態
                is_displayed = other_user_tab.is_displayed()
                is_enabled = other_user_tab.is_enabled()
                self._update_status(f"  > [除錯資訊] 元素是否可見 (is_displayed): {is_displayed}")
                self._update_status(f"  > [除錯資訊] 元素是否啟用 (is_enabled): {is_enabled}")

                if not is_displayed:
                    self._update_status("  > [除錯資訊] 錯誤：元素找到了，但是處於不可見狀態！")
                    raise Exception("目標元素不可見")

                # --- 診斷步驟 3: 執行點擊 ---
                self._update_status("  > 執行 JavaScript 點擊...")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", other_user_tab)
                self._update_status("  > JS 點擊指令已發送。等待2秒讓頁面反應...")
                time.sleep(2) # 等待JS生效

                # --- 診斷步驟 4: 驗證點擊結果 ---
                # 點擊成功後，該元素的 class 應該會包含 'active'
                class_attribute = other_user_tab.get_attribute('class')
                self._update_status(f"  > [除錯資訊] 點擊後，元素的 class 為: '{class_attribute}'")

                if 'active' in class_attribute:
                    self._update_status("  > ✅ [驗證成功] 「其他用戶」頁籤已成功切換！")
                else:
                    self._update_status("  > ❌ [驗證失敗] 點擊未生效，頁籤未切換！嘗試直接呼叫 JS 函式...")
                    # 備用方案：直接呼叫 onclick 的函式
                    driver.execute_script("openTab(event, 'other_tab')")
                    time.sleep(2)
                    class_attribute_after_fallback = other_user_tab.get_attribute('class')
                    self._update_status(f"  > [除錯資訊] 備用方案後，元素的 class 為: '{class_attribute_after_fallback}'")
                    if 'active' not in class_attribute_after_fallback:
                         raise Exception("所有點擊方法均失敗")

            except Exception as e:
                self._update_status(f"  > ❗️ 在點擊「其他用戶」的過程中發生關鍵錯誤: {e}")
                driver.save_screenshot('niceshoppy_debug_error.png')
                st.image('niceshoppy_debug_error.png', caption='除錯過程失敗截圖')
                raise 

            self._update_status("  > 正在尋找 7-11 輸入框...")
            seven_eleven_textarea_xpath = "//textarea[@name='unimart']"
            seven_eleven_textarea = wait.until(EC.element_to_be_clickable((By.XPATH, seven_eleven_textarea_xpath)))
            
            self._update_status(f"  > 找到輸入框，準備貼上 {len(codes_to_process)} 筆代碼...")
            codes_as_string = "\n".join(codes_to_process)
            driver.execute_script("arguments[0].value = arguments[1];", seven_eleven_textarea, codes_as_string)
            self._update_status("  > ✅ 代碼已全部貼上！")
            
            time.sleep(1)
            driver.find_element(By.XPATH, "//button[contains(text(), '產出寄件單')]").click()
            self._update_status("🎉 [完成] 已點擊產出寄件單！")
            time.sleep(5)
            return True
        except Exception as e:
            self._update_status(f"  > ❗️ 蝦皮出貨快手處理過程中發生錯誤: {e}")
            try:
                if driver:
                    driver.save_screenshot('niceshoppy_fatal_error.png')
                    st.image('niceshoppy_fatal_error.png')
            except: pass
            return False
        finally:
            if driver: driver.quit()
    # =========================================================================
    # END: DEBUG-ENHANCED NiceShoppy Automation Function
    # =========================================================================

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
if 'wms_scraping_done' not in st.session_state: st.session_state.wms_scraping_done = False
if 'seven_eleven_codes' not in st.session_state: st.session_state.seven_eleven_codes = []
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state: st.session_state.df_filtered = pd.DataFrame()
if 'report_texts' not in st.session_state: st.session_state.report_texts = {}
if 'duck_index' not in st.session_state: st.session_state.duck_index = 0
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

with main_tab1:
    st.header("步驟一：從 WMS 擷取今日資料")
    if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
        if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
        else: clear_credentials(CREDENTIALS_FILE_WMS)
        st.session_state.wms_scraping_done = False
        st.session_state.seven_eleven_codes = []
        progress_text = st.empty(); progress_duck = st.empty()
        st.session_state.duck_index = 0
        # 假設你有這些圖片檔在本地
        duck_images = ["duck_0.png", "duck_1.png", "duck_2.png", "duck_3.png", "duck_4.png"]
        
        def streamlit_callback(message):
            text = message.replace("  > ", "").replace("...", "")
            if "登入完成" in message and st.session_state.duck_index < 1: st.session_state.duck_index = 1
            elif "進入揀包完成頁面" in message and st.session_state.duck_index < 2: st.session_state.duck_index = 2
            elif "所有頁面資料抓取完畢" in message and st.session_state.duck_index < 3: st.session_state.duck_index = 3
            elif "資料處理完成" in message and st.session_state.duck_index < 4: st.session_state.duck_index = 4
            progress_text.text(f"{text}...")
            # 為了避免找不到圖片檔而出錯，加上檔案存在檢查
            if os.path.exists(duck_images[st.session_state.duck_index]):
                progress_duck.image(duck_images[st.session_state.duck_index])

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
                    time.sleep(1.5); progress_text.empty(); progress_duck.empty()
                    st.success("🎉 WMS 任務完成！")
                else:
                    progress_text.empty(); progress_duck.empty()
                    st.warning("⚠️ WMS 抓取完成，但沒有收到任何資料。")
        except Exception as e:
            progress_text.empty(); progress_duck.empty()
            st.error(f"❌ 執行 WMS 任務時發生致命錯誤："); st.exception(e)

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

with main_tab2:
    st.header("步驟二：處理蝦皮出貨快手訂單")
    if not st.session_state.get('wms_scraping_done', False):
         st.info("請先在「WMS 資料擷取」分頁中成功擷取資料，才能啟用此功能。")
    elif not st.session_state.get('seven_eleven_codes'):
        st.warning("WMS 資料中未找到需要處理的【純 7-11】運送代碼。")
    else:
        st.success(f"✅ 已從 WMS 系統載入 **{len(st.session_state.seven_eleven_codes)}** 筆 **純 7-11** 的運送代碼。")
        st.text_area("待處理代碼預覽", value="\n".join(st.session_state.seven_eleven_codes), height=150)
        
        if st.button("🚀 開始處理蝦皮出貨快手", type="primary", use_container_width=True, disabled=not st.session_state.get('seven_eleven_codes')):
            if shoppy_remember: save_credentials(CREDENTIALS_FILE_SHOPPY, shoppy_username, shoppy_password)
            else: clear_credentials(CREDENTIALS_FILE_SHOPPY)
            
            status_area_shoppy = st.empty()
            
            def shoppy_callback(message): 
                # 使用 st.info 讓訊息框保持可見直到下次更新
                status_area_shoppy.info(message)
            
            # 不再使用 st.spinner，因為回呼函式會處理狀態更新
            try:
                if not shoppy_username or not shoppy_password:
                    st.error("❌ 請務必在側邊欄設定中輸入蝦皮出貨快手的帳號和密碼！")
                else:
                    tool = AutomationTool(status_callback=shoppy_callback)
                    success = tool.run_niceshoppy_automation(shoppy_url, shoppy_username, shoppy_password, st.session_state.seven_eleven_codes)
                    
                    if success:
                        status_area_shoppy.success("🎉 蝦皮出貨快手任務已成功執行！")
                    else:
                        # 錯誤訊息由函式內部透過回呼顯示
                        status_area_shoppy.error("❌ 蝦皮出貨快手任務失敗，請查看上方日誌或截圖。")
            except Exception as e:
                status_area_shoppy.error("❌ 執行蝦皮出貨快手任務時發生致命錯誤：")
                st.exception(e)
