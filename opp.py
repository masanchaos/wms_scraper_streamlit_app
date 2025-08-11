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

    def run_711_order_processing(self, url, username, password, phone_number, codes_to_process):
        """[新功能] 執行 7-11 網站的訂單處理流程"""
        driver = None
        try:
            driver = self._initialize_driver()
            self._update_status("  > 前往 7-11 登入頁面...")
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "UserName"))).send_keys(username)
            driver.find_element(By.ID, "Password").send_keys(password)
            driver.find_element(By.XPATH, "//button[contains(text(), '登入')]").click()
            self._update_status("✅ [成功] 7-11 登入成功！")

            self._update_status("  > 正在輸入電話...")
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "CPhone"))).send_keys(phone_number)
            driver.find_element(By.ID, "btnCPhoneSend").click()
            self._update_status("✅ [成功] 電話輸入完成！")

            self._update_status("  > 準備開始逐筆輸入運送代碼...")
            # 等待主要的輸入框出現
            code_input_xpath = "//input[@id='pcode']"
            confirm_button_xpath = "//button[@id='btnSave']"
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, code_input_xpath)))
            code_input = driver.find_element(By.XPATH, code_input_xpath)
            confirm_button = driver.find_element(By.XPATH, confirm_button_xpath)
            
            total_codes = len(codes_to_process)
            for i, code in enumerate(codes_to_process):
                self._update_status(f"  > 正在處理第 {i+1}/{total_codes} 筆: {code}")
                code_input.clear()
                code_input.send_keys(code)
                confirm_button.click()
                time.sleep(0.5) # 每次點擊後短暫等待，避免操作過快
            
            self._update_status(f"✅ [成功] {total_codes} 筆代碼已全部輸入！")
            
            self._update_status("  > 正在點擊最終的「確認收件」按鈕...")
            final_confirm_button_xpath = "//a[@id='btnConfrim']" # 注意此處可能是 <a> 標籤
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, final_confirm_button_xpath))).click()
            
            self._update_status("🎉 [完成] 所有 7-11 訂單已處理完畢！")
            time.sleep(5) # 暫停讓使用者看到成功訊息
            return True

        except Exception as e:
            self._update_status(f"  > ❗️ 7-11 處理過程中發生錯誤: {e}")
            try:
                driver.save_screenshot('711_processing_error.png')
                st.image('711_processing_error.png')
            except: pass
            return False
        finally:
            if driver: driver.quit()


# ... 其他輔助函式保持不變 ...
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
    
    # [新功能] 儲存 7-11 相關的運送代碼供後續使用
    seven_codes = df_sorted_all[df_sorted_all['寄送方式'].isin(['7-11', '711大物流'])]['主要運送代碼'].tolist()
    st.session_state.seven_eleven_codes = [code for code in seven_codes if code] # 確保不包含空字串

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
if 'seven_eleven_codes' not in st.session_state: st.session_state.seven_eleven_codes = []

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
    
    with st.expander("⚙️ 7-11 刷單網站設定", expanded=True):
        seven_creds = load_credentials(CREDENTIALS_FILE_711)
        seven_url = st.text_input("7-11 網站 URL", value="https://myship.sp88.tw/ECGO/Account/Login?ReturnUrl=%2FECGO%2FC2CPickup")
        seven_username = st.text_input("7-11 帳號", value=seven_creds.get("username", "SSC_008"))
        seven_password = st.text_input("7-11 密碼", value=seven_creds.get("password", "abc123"), type="password")
        seven_phone = st.text_input("7-11 電話", value="0966981112")
        seven_remember = st.checkbox("記住 7-11 帳密", value=bool(seven_creds))
    
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在伺服器上。")

# --- 主頁面 ---
st.title("🚚 WMS & 7-11 自動化工具")

tab1, tab2 = st.tabs(["📊 WMS 資料擷取", "📦 7-11 訂單處理"])

with tab1:
    st.header("步驟一：從 WMS 擷取今日資料")
    if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
        if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
        else: clear_credentials(CREDENTIALS_FILE_WMS)
        st.session_state.scraping_done = False
        st.session_state.seven_eleven_codes = []
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
            st.error(f"❌ 執行 WMS 任務時發生致命錯誤："); st.exception(e)

    if st.session_state.scraping_done:
        st.markdown("---")
        st.header("📊 WMS 擷取結果")
        # ... WMS 結果顯示 UI ...
        restab1, restab2 = st.tabs(["📊 指定項目報告", "📋 所有項目報告"])
        with restab1:
            # ... UI code for filtered report
            pass
        with restab2:
            # ... UI code for all items report
            pass

with tab2:
    st.header("步驟二：處理 7-11 訂單")
    if not st.session_state.seven_eleven_codes:
        st.info("請先在「WMS 資料擷取」分頁中成功擷取資料，才能啟用此功能。")
    else:
        st.success(f"✅ 已從 WMS 系統載入 **{len(st.session_state.seven_eleven_codes)}** 筆 7-11 / 711大物流的運送代碼。")
        st.text_area("待處理代碼預覽", value="\n".join(st.session_state.seven_eleven_codes), height=150)

        if st.button("🚀 開始處理 7-11 訂單", type="primary", use_container_width=True, disabled=not st.session_state.seven_eleven_codes):
            if seven_remember: save_credentials(CREDENTIALS_FILE_711, seven_username, seven_password)
            else: clear_credentials(CREDENTIALS_FILE_711)
            
            status_area_711 = st.empty()
            def seven_callback(message): status_area_711.info(message)
            
            with st.spinner("正在執行 7-11 訂單處理..."):
                try:
                    if not seven_username or not seven_password or not seven_phone:
                        st.error("❌ 請務必在側邊欄設定中輸入 7-11 的帳號、密碼和電話！")
                    else:
                        scraper = WmsScraper(status_callback=seven_callback)
                        success = scraper.run_711_order_processing(seven_url, seven_username, seven_password, seven_phone, st.session_state.seven_eleven_codes)
                        if success:
                            status_area_711.success("🎉 所有 7-11 訂單已成功處理！")
                        else:
                            status_area_711.error("❌ 7-11 訂單處理失敗，請查看上方日誌或截圖。")
                except Exception as e:
                    status_area_711.error("❌ 執行 7-11 任務時發生致命錯誤："); st.exception(e)
