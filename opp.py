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
class WmsScraper:
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
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "app")))
        self._update_status("✅ [成功] WMS 登入完成！")
        time.sleep(5)
    
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
            current_page_rows = driver.find_elements(By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")
            if not current_page_rows: break
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
                WebDriverWait(driver, 20).until(EC.staleness_of(current_page_rows[0]))
                WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, item_list_container_xpath)))
            except Exception: break
        self._update_status("  > 所有頁面資料抓取完畢。")
        return all_data

    def run_wms_scrape(self, url, username, password):
        """執行完整的 WMS 爬蟲流程"""
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            time.sleep(2)
            data = self._scrape_data(driver)
            self._update_status("✅ 所有資料抓取完成！")
            return pd.DataFrame(data)
        finally:
            if driver: driver.quit()

    def run_711_login_test(self, url, username, password):
        """[新功能] 執行 7-11 網站的登入測試流程"""
        driver = None
        try:
            driver = self._initialize_driver()
            self._update_status("  > 正在前往 7-11 登入頁面...")
            driver.get(url)
            
            # 根據 7-11 網站的 HTML 結構來定位元素 (常見的 id/name)
            account_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "UserName")))
            password_input = driver.find_element(By.ID, "Password")
            login_button = driver.find_element(By.XPATH, "//button[contains(text(), '登入')]")
            
            self._update_status("  > 正在輸入帳號密碼...")
            account_input.send_keys(username)
            password_input.send_keys(password)
            
            self._update_status("  > 正在點擊登入...")
            login_button.click()
            
            # 登入成功後，通常會跳轉頁面，我們可以等待某個登入後才有的元素出現
            # 這裡我們等待 "訂單管理" 這個連結出現，作為成功的標誌
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "orderManage")))
            self._update_status("✅ [成功] 7-11 網站登入成功！")
            time.sleep(3) # 暫停一下，方便觀察
            return True

        except Exception as e:
            self._update_status(f"  > ❗️ 7-11 登入失敗: {e}")
            # 出錯時截圖，這在部署環境中特別有用
            driver.save_screenshot('711_login_error.png')
            st.image('711_login_error.png')
            return False
        finally:
            if driver: driver.quit()

# ... generate_report_text, process_and_output_data, 憑證處理函式 ...
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
            method_part = f"{row['寄送方式']}:"
            count_part = str(row['數量'])
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
    st.session_state.report_texts['filtered_summary'], st.session_state.report_texts['filtered_full'] = generate_report_text(df_filtered, display_timestamp, "指定項目分組統計")
    st.session_state.report_texts['all_summary'], st.session_state.report_texts['all_full'] = generate_report_text(df_sorted_all, display_timestamp, "所有項目分組統計")
    st.session_state.file_timestamp = now.strftime("%y%m%d%H%M")
    status_callback("✅ 資料處理完成！")
CREDENTIALS_FILE_WMS = "credentials_wms.json"
CREDENTIALS_FILE_711 = "credentials_711.json"
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

st.set_page_config(page_title="WMS & 7-11 工具", page_icon="🚚", layout="wide")
if 'scraping_done' not in st.session_state: st.session_state.scraping_done = False
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state: st.session_state.df_filtered = pd.DataFrame()
if 'report_texts' not in st.session_state: st.session_state.report_texts = {}

# --- 側邊欄 ---
with st.sidebar:
    st.image("https://www.jenjan.com.tw/images/logo.svg", width=200)
    st.header("⚙️ WMS 設定")
    wms_creds = load_credentials(CREDENTIALS_FILE_WMS)
    wms_url = st.text_input("WMS 網頁 URL", value="https://wms.jenjan.com.tw/")
    wms_username = st.text_input("WMS 帳號", value=wms_creds.get("username", ""))
    wms_password = st.text_input("WMS 密碼", value=wms_creds.get("password", ""), type="password")
    wms_remember = st.checkbox("記住 WMS 帳密", value=bool(wms_creds))
    st.markdown("---")
    
    # [新功能] 7-11 設定區
    with st.expander("⚙️ 7-11 刷單網站設定", expanded=False):
        seven_creds = load_credentials(CREDENTIALS_FILE_711)
        seven_url = st.text_input("7-11 網站 URL", value="https://myship.sp88.tw/ECGO/Account/Login?ReturnUrl=%2FECGO%2FC2CPickup")
        seven_username = st.text_input("7-11 帳號", value=seven_creds.get("username", "SSC_008"))
        seven_password = st.text_input("7-11 密碼", value=seven_creds.get("password", "abc123"), type="password")
        seven_remember = st.checkbox("記住 7-11 帳密", value=bool(seven_creds))
    
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在伺服器上。")

# --- 主頁面 ---
st.title("🚚 WMS & 7-11 自動化工具")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("WMS 資料擷取")
    if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
        if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
        else: clear_credentials(CREDENTIALS_FILE_WMS)
        st.session_state.scraping_done = False
        progress_text = st.empty(); progress_duck = st.empty()
        st.session_state.duck_index = 0
        duck_images = ["duck_0.png", "duck_1.png", "duck_2.png", "duck_3.png", "duck_4.png"]
        def streamlit_callback(message):
            text = message.replace("  > ", "").replace("...", "")
            if "登入完成" in message and st.session_state.duck_index < 1: st.session_state.duck_index = 1
            elif "進入揀包完成頁面" in message and st.session_state.duck_index < 2: st.session_state.duck_index = 2
            elif "所有頁面資料抓取完畢" in message and st.session_state.duck_index < 3: st.session_state.duck_index = 3
            elif "資料處理完成" in message and st.session_state.duck_index < 4: st.session_state.duck_index = 4
            progress_text.text(f"{text}..."); progress_duck.image(duck_images[st.session_state.duck_index])
        try:
            if not wms_username or not wms_password:
                st.error("❌ 請務必輸入 WMS 帳號和密碼！")
            else:
                streamlit_callback("準備開始... 🐣")
                scraper = WmsScraper(status_callback=streamlit_callback)
                result_df = scraper.run_wms_scrape(wms_url, wms_username, wms_password)
                if not result_df.empty:
                    process_and_output_data(result_df, streamlit_callback)
                    st.session_state.scraping_done = True
                    time.sleep(1.5)
                    progress_text.empty(); progress_duck.empty()
                    st.success("🎉 WMS 任務完成！")
                else:
                    progress_text.empty(); progress_duck.empty()
                    st.warning("⚠️ WMS 抓取完成，但沒有收到任何資料。")
        except Exception as e:
            progress_text.empty(); progress_duck.empty()
            st.error(f"❌ 執行 WMS 任務時發生致命錯誤：")
            st.exception(e)

with col2:
    st.subheader("7-11 網站操作")
    if st.button("🔬 測試登入 7-11 網站", use_container_width=True):
        if seven_remember: save_credentials(CREDENTIALS_FILE_711, seven_username, seven_password)
        else: clear_credentials(CREDENTIALS_FILE_711)
        status_area = st.empty()
        def seven_callback(message): status_area.info(message)
        with st.spinner("正在執行 7-11 登入測試..."):
            try:
                 if not seven_username or not seven_password:
                     st.error("❌ 請務必輸入 7-11 帳號和密碼！")
                 else:
                    scraper = WmsScraper(status_callback=seven_callback)
                    success = scraper.run_711_login_test(seven_url, seven_username, seven_password)
                    if success:
                        status_area.success("🎉 7-11 登入成功！")
                    else:
                        status_area.error("❌ 7-11 登入失敗，請檢查日誌或截圖。")
            except Exception as e:
                status_area.error("❌ 執行 7-11 登入時發生致命錯誤：")
                st.exception(e)

if st.session_state.scraping_done:
    st.markdown("---")
    st.header("📊 WMS 擷取結果")
    tab1, tab2 = st.tabs(["📊 指定項目報告", "📋 所有項目報告"])
    with tab1:
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
    with tab2:
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
