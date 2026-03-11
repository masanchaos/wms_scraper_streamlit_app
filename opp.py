import streamlit as st
import pandas as pd
import datetime
import time
import json
import os
import traceback
from shutil import which
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components
import html
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

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
# 核心爬蟲邏輯
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback: 
            self.status_callback(message)

    def _initialize_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") # 使用新版無頭模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--lang=zh-TW,zh")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # 尋找由 packages.txt (apt-get) 安裝的 chromium 執行檔路徑
        chrome_binary = which("chromium") or which("chromium-browser")
        if chrome_binary:
            chrome_options.binary_location = chrome_binary
            self._update_status(f"  > 找到 Chromium 路徑: {chrome_binary}")

        self._update_status("  > 正在初始化 WebDriver...")
        
        try:
            # 優先嘗試使用從 packages.txt 安裝的 chromium-driver
            chromedriver_path = which("chromedriver")
            if chromedriver_path:
                self._update_status(f"  > 使用系統內建 ChromeDriver: {chromedriver_path}")
                service = Service(executable_path=chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self._update_status("  > 未找到系統 ChromeDriver，啟動 webdriver_manager 自動下載...")
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            self._update_status(f"❌ WebDriver 初始化失敗: {e}")
            raise e

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
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "page-container")))
        self._update_status("✅ [成功] WMS 登入完成！")
        time.sleep(3)
        
    def _navigate_to_picking_complete(self, driver):
        self._update_status("  > 尋找導覽菜單...")
        picking_management_xpath = "//a[@href='/admin/pickup']"
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()
        
        self._update_status("  > 正在等待並切換至「揀包完成/Picked」分頁...")
        # 等待一下讓右側畫面初步渲染
        time.sleep(3)
        
        # 恢復使用最準確的 XPath：尋找帶有 btn class 且內容包含 Picked 或 揀包完成 的 div
        picking_complete_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '揀包完成') or contains(., 'Picked') or contains(., 'Complete'))]"
        
        try:
            tab_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, picking_complete_tab_xpath))
            )
            
            # 確保滾動到該分頁按鈕並點擊
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab_element)
            time.sleep(1)
            
            # 使用 JS 點擊最保險
            driver.execute_script("arguments[0].click();", tab_element)
            
            self._update_status("✅ [成功] 已點擊揀包完成頁面！等待系統切換...")
            # 強制等待系統切換 Tab（非常重要，避免點了立刻按查詢導致撈到上一個 Tab 的資料）
            time.sleep(3) 
            
        except TimeoutException as e:
            # 發生超時找不到元素時，立刻截圖！
            driver.save_screenshot("error_screenshot.png")
            self._update_status("📸 [除錯] 找不到「揀包完成」或「Picked」按鈕，已擷取錯誤發生時的畫面截圖。")
            raise e

    def _scrape_data(self, driver):
        self._update_status("  > 點擊查詢按鈕以載入資料...")
        query_button_xpath = "//div[contains(@class, 'btn-primary')]"
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, query_button_xpath))).click()
        
        loading_spinner_xpath = "//div[contains(@class, 'j-loading')]"
        WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
        self._update_status("  > 資料已初步載入。")
        
        all_pages_data = []
        page_count = 1
        item_list_container_xpath = "//div[contains(@class, 'list-items')]"
        counter_label_xpath = "(//div[contains(@class, 'item') and .//label[contains(@class, 'm-check')]])[1]//label[contains(@class, 'm-check')]"
        
        while True:
            self._update_status(f"  > 準備抓取第 {page_count} 頁的資料...")
            label_text_before_click = ""
            
            try:
                counter_label_element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, counter_label_xpath))
                )
                label_text_before_click = counter_label_element.text
                self._update_status(f"  > 第 {page_count} 頁頁面標記: '{label_text_before_click.strip()}'")
                current_page_rows = driver.find_elements(By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")
                self._update_status(f"  > 找到 {len(current_page_rows)} 筆項目，開始解析...")
            except TimeoutException:
                self._update_status(f"  > 在第 {page_count} 頁未找到任何項目，抓取結束。")
                break

            single_page_data = []
            for row in current_page_rows:
                try:
                    shipping_method = row.find_element(By.XPATH, "./div[2]/div[3]").text.strip()
                    tracking_code_input = row.find_element(By.XPATH, "./div[2]/div[4]//input")
                    tracking_code = tracking_code_input.get_property('value').strip()
                    status = '正常'
                    try:
                        canceled_div = row.find_elements(By.XPATH, ".//div[contains(@class, 'm-pre-dot') and contains(text(), '已取消')]")
                        if canceled_div: status = '已取消'
                    except Exception: pass
                    
                    if shipping_method or tracking_code:
                        single_page_data.append({
                            "寄送方式": shipping_method, "主要運送代碼": tracking_code, "狀態": status
                        })
                except Exception:
                    continue
            
            all_pages_data.append(single_page_data)
            total_items_collected = sum(len(page) for page in all_pages_data)
            self._update_status(f"✅ 第 {page_count} 頁解析完畢。本頁 {len(single_page_data)} 筆，累計 {total_items_collected} 筆。")

            try:
                # 支援中文「下一頁」與英文「Next」
                next_button_xpath = "//button[normalize-space()='下一頁' or normalize-space()='Next']"
                next_button_element = driver.find_element(By.XPATH, next_button_xpath)
                
                if next_button_element.get_attribute('disabled'):
                    self._update_status("  > 「下一頁」按鈕已禁用，抓取結束。")
                    break
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button_element)
                time.sleep(0.2)
                next_button_element.click()
                self._update_status(f"  > 已點擊「下一頁」，正在等待頁面標記更新...")

                wait = WebDriverWait(driver, 30)
                wait.until(lambda d: d.find_element(By.XPATH, counter_label_xpath).text != label_text_before_click)
                self._update_status(f"✅ [成功] 頁面標記已更新，第 {page_count + 1} 頁已載入！")
                page_count += 1
            except (TimeoutException, NoSuchElementException, Exception):
                self._update_status(f"  > 翻頁條件未滿足或出錯，抓取結束。")
                break
                
        self._update_status("  > 所有頁面資料抓取完畢，正在合併資料...")
        final_data = [item for page_list in all_pages_data for item in page_list]
        total_final_items = len(final_data)
        self._update_status(f"  > 資料合併完成，最終總筆數: {total_final_items}")
        
        return final_data

    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            data = self._scrape_data(driver)
            return pd.DataFrame(data)
        except Exception as e:
            # 將例外情況拋出給外部捕捉，這樣能記錄完整 traceback
            raise e
        finally:
            if driver: driver.quit()

# =================================================================================
# 資料處理與報告生成
# =================================================================================
def generate_report_text(df_to_process, display_timestamp, report_title, show_status=False):
    df_display = df_to_process.copy()
    
    cols_to_drop = ['分組']
    if not show_status:
        cols_to_drop.append('狀態')
        
    df_display = df_display.drop(columns=[c for c in cols_to_drop if c in df_display.columns], errors='ignore')

    if df_display.empty or len(df_display) == 0:
        summary = f"--- {report_title} ---\n\n此分類下無資料。"
        full_report = f"擷取時間: {display_timestamp} (台北時間)\n\n{summary}"
        return summary, full_report
    
    summary_lines = ["==============================", f"=== {report_title} ===", "=============================="]
    
    summary_df = df_display.groupby('寄送方式', observed=False).size().reset_index(name='數量')
    total_count = len(df_display)
    max_len = summary_df['寄送方式'].astype(str).str.len().max() + 2 if not summary_df.empty else 10
    
    for _, row in summary_df.iterrows():
        if row['數量'] > 0:
            method_part = f"{row['寄送方式']}:"
            count_part = str(row['數量'])
            line = f"{method_part:<{max_len}} {count_part:>8}"
            summary_lines.append(line)
                
    summary_lines.append("\n------------------------------")
    summary_lines.append(f"總計: {total_count}")
    summary_text = "\n".join(summary_lines)
    
    details_text = df_display.to_string(index=False)
    
    full_report_text = (f"擷取時間: {display_timestamp} (台北時間)\n\n{summary_text}\n\n"
                      "==============================\n======== 資 料 明 細 ========\n==============================\n\n"
                      f"{details_text}")
    return summary_text, full_report_text

def process_and_output_data(df, status_callback):
    now = datetime.datetime.now(ZoneInfo("Asia/Taipei"))
    display_timestamp = now.strftime("%Y-%m-%d %H:%M")

    status_callback("  > 拆分已取消與正常訂單...")
    df_canceled = df[df['狀態'] == '已取消'].copy()
    df_processing = df[df['狀態'] != '已取消'].copy()
    
    status_callback("  > 細分正常訂單組...")
    df_processing['主要運送代碼'] = df_processing['主要運送代碼'].astype(str)
    condition = (df_processing['寄送方式'] == '7-11') & (df_processing['主要運送代碼'].str.match(r'^\d', na=False))
    df_processing.loc[condition, '寄送方式'] = '711大物流'
    
    group_mapping = {
        '7-11': '第一組', '711大物流': '第一組', '全家': '第一組', '萊爾富': '第一組', '萊爾福': '第一組', 'OK': '第一組', '蝦皮店到店': '第一組',
        '蝦皮隔日配': '第二組', '蝦皮店到家': '第二組',
        '順豐特快': '第三組', '順豐國際': '第三組',
        '黑貓': '第四組',
        '新竹物流': '第五組'
    }
    
    df_processing['分組'] = df_processing['寄送方式'].map(group_mapping).fillna('其他')
    df_canceled['分組'] = df_canceled['寄送方式'].map(group_mapping).fillna('其他')
    df['分組'] = df['寄送方式'].map(group_mapping).fillna('其他')
    
    priority_order = [
        '7-11', '711大物流', '全家', '萊爾富', '萊爾福', 'OK', '蝦皮店到店', 
        '蝦皮隔日配', '蝦皮店到家', 
        '順豐特快', '順豐國際', 
        '黑貓', 
        '新竹物流'
    ]
    
    processing_methods = df_processing['寄送方式'].unique().tolist()
    processing_order = [m for m in priority_order if m in processing_methods] + sorted([m for m in processing_methods if m not in priority_order])
    df_processing['寄送方式'] = pd.Categorical(df_processing['寄送方式'], categories=processing_order, ordered=True)
    
    group_order = ['第一組', '第二組', '第三組', '第四組', '第五組', '其他']
    df_processing['分組'] = pd.Categorical(df_processing['分組'], categories=group_order, ordered=True)
    df_processing_sorted = df_processing.sort_values(by=['分組', '寄送方式'])
    
    st.session_state.final_df = df_processing_sorted
    st.session_state.df_canceled = df_canceled
    st.session_state.file_timestamp = now.strftime("%y%m%d%H%M")
    
    reports = {}
    for g in group_order:
        df_g = df_processing_sorted[df_processing_sorted['分組'] == g]
        if not df_g.empty:
            reports[g] = generate_report_text(df_g, display_timestamp, f"{g} 統計")[1]
        else:
            reports[g] = None
            
    reports['all'] = generate_report_text(df_processing_sorted, display_timestamp, "所有正常項目統計")[1]
    reports['canceled'] = generate_report_text(df_canceled, display_timestamp, "已取消項目統計", show_status=True)[1]
    
    st.session_state.report_texts = reports
    status_callback("✅ 資料處理完成！")

CREDENTIALS_FILE_WMS = "credentials_wms.json"
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

# 寫入 Log 到 session_state 的輔助函數
def append_to_log(message):
    timestamp = datetime.datetime.now(ZoneInfo("Asia/Taipei")).strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    if 'app_logs' not in st.session_state:
        st.session_state.app_logs = []
    st.session_state.app_logs.append(log_line)

# =================================================================================
# Streamlit 前端介面
# =================================================================================

st.set_page_config(page_title="WMS 工具", page_icon="🚚", layout="wide")
if 'wms_scraping_done' not in st.session_state: st.session_state.wms_scraping_done = False
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_canceled' not in st.session_state: st.session_state.df_canceled = pd.DataFrame()
if 'report_texts' not in st.session_state: st.session_state.report_texts = {}
if 'duck_index' not in st.session_state: st.session_state.duck_index = 0
if 'app_logs' not in st.session_state: st.session_state.app_logs = []

with st.sidebar:
    st.image("https://www.jenjan.com.tw/images/logo.svg", width=200)
    with st.expander("⚙️ WMS 設定", expanded=True):
        wms_creds = load_credentials(CREDENTIALS_FILE_WMS)
        wms_url = st.text_input("WMS URL", value="https://wms.jenjan.com.tw/", key="wms_url")
        wms_username = st.text_input("WMS 帳號", value=wms_creds.get("username", ""), key="wms_user")
        wms_password = st.text_input("WMS 密碼", value=wms_creds.get("password", ""), type="password", key="wms_pass")
        wms_remember = st.checkbox("記住 WMS 帳密", value=bool(wms_creds), key="wms_rem")
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在伺服器上。")

st.title("🚚 WMS 自動化資料擷取工具")
st.header("從 WMS 擷取今日資料")

if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
    if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
    else: clear_credentials(CREDENTIALS_FILE_WMS)
    
    # 初始化狀態與清空 Log
    st.session_state.wms_scraping_done = False
    st.session_state.app_logs = [] 
    st.session_state.duck_index = 0
    
    progress_text = st.empty()
    progress_duck = st.empty()
    duck_images = ["duck_0.png", "duck_1.png", "duck_2.png", "duck_3.png", "duck_4.png"]
    
    def streamlit_callback(message):
        # 同時寫入介面文字與系統日誌
        append_to_log(message)
        text = message.replace("  > ", "").replace("...", "")
        
        if "登入完成" in message and st.session_state.duck_index < 1: st.session_state.duck_index = 1
        elif "進入揀包完成頁面" in message and st.session_state.duck_index < 2: st.session_state.duck_index = 2
        elif "所有頁面資料抓取完畢" in message and st.session_state.duck_index < 3: st.session_state.duck_index = 3
        elif "資料處理完成" in message and st.session_state.duck_index < 4: st.session_state.duck_index = 4
        
        progress_text.info(f"{text}...")
        if os.path.exists(duck_images[st.session_state.duck_index]):
            progress_duck.image(duck_images[st.session_state.duck_index])

    try:
        if not wms_username or not wms_password:
            st.error("❌ 請務必輸入 WMS 帳號和密碼！")
            append_to_log("❌ 錯誤：未輸入帳號或密碼")
        else:
            streamlit_callback("準備開始... 🐣")
            tool = AutomationTool(status_callback=streamlit_callback)
            result_df = tool.run_wms_scrape(wms_url, wms_username, wms_password)
            
            if result_df is not None and not result_df.empty:
                process_and_output_data(result_df, streamlit_callback)
                st.session_state.wms_scraping_done = True
                time.sleep(1); progress_text.empty(); progress_duck.empty()
                st.success("🎉 WMS 任務完成！")
            elif result_df is not None and result_df.empty:
                progress_text.empty(); progress_duck.empty()
                st.warning("⚠️ WMS 抓取完成，但沒有收到任何資料。")
                append_to_log("⚠️ 警告：抓取完成，但回傳資料為空。")
            else: 
                progress_text.empty(); progress_duck.empty()
                st.error("❌ 執行 WMS 任務時發生預期外錯誤。")
                append_to_log("❌ 錯誤：回傳結果為 None。")
                
    except Exception as e:
        # 捕捉最詳細的錯誤追蹤碼並存入 Log
        error_traceback = traceback.format_exc()
        append_to_log(f"❌ 發生致命例外錯誤:\n{error_traceback}")
        progress_text.empty(); progress_duck.empty()
        st.error("❌ 執行 WMS 任務時發生致命錯誤，請查看最下方的「系統日誌」！")
        
        # 檢查有沒有剛拍下來的截圖，有的話就顯示出來
        if os.path.exists("error_screenshot.png"):
            st.warning("📸 以下是機器人當下看到的畫面：")
            st.image("error_screenshot.png")
            # 顯示完就刪掉，避免下次干擾
            os.remove("error_screenshot.png") 

if st.session_state.get('wms_scraping_done', False):
    st.markdown("---")
    st.header("📊 WMS 擷取結果")
    
    custom_header = st.text_area("✍️ 置頂自訂文字 (只要有輸入，複製或下載任一頁面的報告時，都會自動加在最頂端)", 
                                 value="", height=80, placeholder="例如：今日出貨請確認以下資料無誤...")
    
    canceled_count = len(st.session_state.df_canceled)
    if canceled_count > 0:
        st.error(f"⚠️ 注意！偵測到 {canceled_count} 筆「已取消」的訂單，請務必確認！", icon="🚨")

    groups = ['第一組', '第二組', '第三組', '第四組', '第五組', '其他']
    tab_titles = ['第一組', '第二組', '第三組', '第四組', '第五組', '其他'] + ["📋 所有項目", f"❌ 已取消訂單 ({canceled_count})" if canceled_count > 0 else "❌ 已取消訂單"]
    tabs = st.tabs(tab_titles)
    
    # 這裡的迴圈使用 index 匹配，避免 groups 名稱錯誤影響標籤
    groups_for_loop = ['第一組', '第二組', '第三組', '第四組', '第五組', '其他']
    for i, g in enumerate(groups_for_loop):
        with tabs[i]:
            if st.session_state.report_texts.get(g):
                raw_text = st.session_state.report_texts[g]
                combined_text = f"{custom_header}\n\n{raw_text}" if custom_header.strip() else raw_text
                
                df_g = st.session_state.final_df[st.session_state.final_df['分組'] == g]
                
                col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
                with col1: create_copy_button(combined_text, f"一鍵複製 {g} 報告", key=f"copy_{g}")
                with col2:
                    st.download_button("下載 CSV", df_g.drop(columns=['分組', '狀態'], errors='ignore').to_csv(index=False, encoding='utf-8-sig'), f"{g}_{st.session_state.file_timestamp}.csv", use_container_width=True)
                with col3:
                    st.download_button("下載 TXT", combined_text.encode('utf-8'), f"{g}_{st.session_state.file_timestamp}.txt", use_container_width=True)
                st.text_area("預覽內容", value=combined_text, height=450, key=f"text_{g}", label_visibility="collapsed")
            else:
                st.info(f"{g} 目前無資料。")
                
    with tabs[6]:
        raw_text = st.session_state.report_texts.get('all', '')
        if raw_text:
            combined_text = f"{custom_header}\n\n{raw_text}" if custom_header.strip() else raw_text
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            with col1: create_copy_button(combined_text, "一鍵複製所有項目", key="copy_all")
            with col2:
                st.download_button("下載 CSV", st.session_state.final_df.drop(columns=['分組', '狀態'], errors='ignore').to_csv(index=False, encoding='utf-8-sig'), f"ALL_{st.session_state.file_timestamp}.csv", use_container_width=True)
            with col3:
                st.download_button("下載 TXT", combined_text.encode('utf-8'), f"ALL_{st.session_state.file_timestamp}.txt", use_container_width=True)
            st.text_area("預覽內容", value=combined_text, height=450, key="text_all", label_visibility="collapsed")
        else:
            st.info("目前無資料。")

    with tabs[7]:
        if canceled_count > 0:
            raw_text = st.session_state.report_texts.get('canceled', '')
            combined_text = f"{custom_header}\n\n{raw_text}" if custom_header.strip() else raw_text
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            with col1: create_copy_button(combined_text, "一鍵複製已取消", key="copy_canceled")
            with col2:
                st.download_button("下載 CSV", st.session_state.df_canceled.drop(columns=['分組'], errors='ignore').to_csv(index=False, encoding='utf-8-sig'), f"CANCELED_{st.session_state.file_timestamp}.csv", use_container_width=True)
            with col3:
                st.download_button("下載 TXT", combined_text.encode('utf-8'), f"CANCELED_{st.session_state.file_timestamp}.txt", use_container_width=True)
            st.text_area("預覽內容", value=combined_text, height=450, key="text_canceled", label_visibility="collapsed")
        else:
            st.info("沒有已取消的訂單。")

# =================================================================================
# 系統日誌顯示區塊 (永遠顯示在最下方)
# =================================================================================
st.markdown("---")
st.subheader("🛠️ 系統日誌 (Logs)")
if st.session_state.app_logs:
    full_log_text = "\n".join(st.session_state.app_logs)
    create_copy_button(full_log_text, "📋 一鍵複製完整日誌以供除錯", key="copy_sys_logs")
    st.text_area("日誌內容：", value=full_log_text, height=300, key="sys_log_area", label_visibility="collapsed")
else:
    st.info("目前尚無執行日誌。按下「開始擷取」後這裡會記錄所有系統狀態與錯誤。")
