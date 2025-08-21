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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
# 核心爬蟲邏輯 (已修正架構)
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
            
            for row in current_page_rows:
                try:
                    shipping_method = row.find_element(By.XPATH, "./div[2]/div[3]").text.strip()
                    tracking_code_input = row.find_element(By.XPATH, "./div[2]/div[4]//input")
                    tracking_code = tracking_code_input.get_property('value').strip()

                    # <<< CHANGE START: 新增狀態欄位以判斷訂單是否已取消 >>>
                    status = '正常'
                    try:
                        # 使用 find_elements 避免在找不到元素時報錯
                        canceled_div = row.find_elements(By.XPATH, ".//div[contains(@class, 'm-pre-dot') and contains(text(), '已取消')]")
                        if canceled_div: # 如果列表不是空的，表示找到了 "已取消" 標籤
                            status = '已取消'
                    except Exception:
                        pass # 即使檢查出錯，也當作正常訂單處理
                    # <<< CHANGE END >>>
                    
                    if shipping_method or tracking_code:
                        all_data.append({
                            "寄送方式": shipping_method,
                            "主要運送代碼": tracking_code,
                            "狀態": status # 將狀態加入資料中
                        })
                except Exception:
                    continue # 如果某一行有問題，跳過並繼續處理下一行
            
            try:
                next_button_xpath = "//button[normalize-space()='下一頁' or normalize-space()='Next']"
                next_button = driver.find_element(By.XPATH, next_button_xpath)
                if next_button.get_attribute('disabled'):
                    self._update_status("  > 「下一頁」按鈕已禁用，抓取結束。")
                    break
                
                list_container = driver.find_element(By.XPATH, item_list_container_xpath)
                
                driver.execute_script("arguments[0].click();", next_button)
                page_count += 1
                
                self._update_status(f"  > 等待第 {page_count} 頁刷新...")
                WebDriverWait(driver, 20).until(EC.staleness_of(list_container))
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")))
                self._update_status(f"  > 第 {page_count} 頁內容已成功刷新。")
                
            except NoSuchElementException:
                self._update_status("  > 未找到「下一頁」按鈕，抓取結束。")
                break
            except TimeoutException:
                self._update_status(f"  > 等待第 {page_count} 頁刷新超時，抓取結束。")
                break
            except Exception as e:
                self._update_status(f"  > 翻頁時發生未知錯誤 ({e})，抓取結束。")
                break
                
        self._update_status("  > 所有頁面資料抓取完畢。")
        return all_data

    # --- Main Execution Flow ---
    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_driver()
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            time.sleep(2)
            data = self._scrape_data(driver)
            return pd.DataFrame(data)
        except Exception as e:
            self._update_status(f"❌ WMS 抓取過程中發生錯誤: {e}")
            return None
        finally:
            if driver: driver.quit()

# =================================================================================
# 資料處理與報告生成
# =================================================================================
def generate_report_text(df_to_process, display_timestamp, report_title):
    # <<< CHANGE: 移除 "狀態" 欄位，避免顯示在報告中 >>>
    df_display = df_to_process.drop(columns=['狀態'], errors='ignore')

    if df_display.empty:
        summary = f"--- {report_title} ---\n\n此分類下無資料。"
        full_report = f"擷取時間: {display_timestamp} (台北時間)\n\n{summary}"
        return summary, full_report
    
    summary_df = df_display.groupby('寄送方式', observed=False).size().reset_index(name='數量')
    total_count = len(df_display)
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
    details_text = df_display.to_string(index=False)
    full_report_text = (f"擷取時間: {display_timestamp} (台北時間)\n\n{summary_text}\n\n"
                        "==============================\n======== 資 料 明 細 ========\n==============================\n\n"
                        f"{details_text}")
    return summary_text, full_report_text

def process_and_output_data(df, status_callback):
    now = datetime.datetime.now(ZoneInfo("Asia/Taipei"))
    display_timestamp = now.strftime("%Y-%m-%d %H:%M")

    # <<< CHANGE START: 根據 "狀態" 欄位將 DataFrame 拆分 >>>
    status_callback("  > 拆分已取消與正常訂單...")
    df_canceled = df[df['狀態'] == '已取消'].copy()
    df_processing = df[df['狀態'] != '已取消'].copy()
    # <<< CHANGE END >>>

    # --- 後續的所有處理，都只針對 df_processing ---
    status_callback("  > 細分組...")
    df_processing['主要運送代碼'] = df_processing['主要運送代碼'].astype(str)
    condition = (df_processing['寄送方式'] == '7-11') & (df_processing['主要運送代碼'].str.match(r'^\d', na=False))
    df_processing.loc[condition, '寄送方式'] = '711大物流'
    
    priority_order = ['7-11', '711大物流', '全家', '萊爾富', 'OK', '蝦皮店到店', '蝦皮店到家']
    all_methods = df_processing['寄送方式'].unique().tolist()
    final_order = [m for m in priority_order if m in all_methods] + sorted([m for m in all_methods if m not in priority_order])
    df_processing['寄送方式'] = pd.Categorical(df_processing['寄送方式'], categories=final_order, ordered=True)
    
    df_sorted_all = df_processing.sort_values(by='寄送方式')
    default_methods = ['7-11', '711大物流', '全家', '萊爾富', 'OK', '蝦皮店到店', '蝦皮店到家']
    df_filtered = df_sorted_all[df_sorted_all['寄送方式'].isin(default_methods)]
    
    # --- 將處理好的資料存入 session_state ---
    st.session_state.df_filtered = df_filtered
    st.session_state.final_df = df_sorted_all
    st.session_state.df_canceled = df_canceled # 儲存已取消的 DataFrame

    # --- 產生三份報告 ---
    st.session_state.report_texts = {}
    st.session_state.report_texts['filtered_full'] = generate_report_text(df_filtered, display_timestamp, "指定項目分組統計")[1]
    st.session_state.report_texts['all_full'] = generate_report_text(df_sorted_all, display_timestamp, "所有項目分組統計")[1]
    st.session_state.report_texts['canceled_full'] = generate_report_text(df_canceled, display_timestamp, "已取消項目統計")[1]
    
    st.session_state.file_timestamp = now.strftime("%y%m%d%H%M")
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

# =================================================================================
# Streamlit 前端介面
# =================================================================================

st.set_page_config(page_title="WMS 工具", page_icon="🚚", layout="wide")
# --- 初始化 session_state ---
if 'wms_scraping_done' not in st.session_state: st.session_state.wms_scraping_done = False
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state: st.session_state.df_filtered = pd.DataFrame()
if 'df_canceled' not in st.session_state: st.session_state.df_canceled = pd.DataFrame() # <<< 新增
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
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在伺服器上。")

st.title("🚚 WMS 自動化資料擷取工具")
st.header("從 WMS 擷取今日資料")

if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
    if wms_remember: save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
    else: clear_credentials(CREDENTIALS_FILE_WMS)
    
    st.session_state.wms_scraping_done = False
    progress_text = st.empty(); progress_duck = st.empty()
    st.session_state.duck_index = 0
    
    duck_images = ["duck_0.png", "duck_1.png", "duck_2.png", "duck_3.png", "duck_4.png"]
    
    def streamlit_callback(message):
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
            else: 
                progress_text.empty(); progress_duck.empty()
                st.error("❌ 執行 WMS 任務時發生錯誤，請查看日誌。")

    except Exception as e:
        progress_text.empty(); progress_duck.empty()
        st.error(f"❌ 執行 WMS 任務時發生致命錯誤："); st.exception(e)

if st.session_state.get('wms_scraping_done', False):
    st.markdown("---")
    st.header("📊 WMS 擷取結果")
    
    # <<< CHANGE: 從 2 個分頁增加到 3 個 >>>
    restab1, restab2, restab3 = st.tabs(["📊 指定項目報告", "📋 所有項目報告", "❌ 已取消訂單"])
    
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
        st.text_area("報告內容", value=st.session_state.report_texts.get('filtered_full', '無資料'), height=500, label_visibility="collapsed", key="text-filtered")
        
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
        st.text_area("報告內容", value=st.session_state.report_texts.get('all_full', '無資料'), height=500, label_visibility="collapsed", key="text-all")

    # <<< CHANGE START: 新增已取消訂單的分頁內容 >>>
    with restab3:
        st.subheader("已取消訂單統計與明細")
        if not st.session_state.df_canceled.empty:
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            with col1: create_copy_button(st.session_state.report_texts.get('canceled_full', ''), "一鍵複製報告", key="copy-btn-canceled")
            with col2:
                # 移除 "狀態" 欄位再下載
                csv_data_canceled = st.session_state.df_canceled.drop(columns=['狀態'], errors='ignore').to_csv(index=False, encoding='utf-8-sig')
                st.download_button(label="下載 CSV (已取消)", data=csv_data_canceled,
                                   file_name=f"picking_data_CANCELED_{st.session_state.file_timestamp}.csv", mime='text/csv', use_container_width=True)
            with col3:
                st.download_button(label="下載 TXT (已取消)", data=st.session_state.report_texts.get('canceled_full', '').encode('utf-8'),
                                   file_name=f"picking_data_CANCELED_{st.session_state.file_timestamp}.txt", mime='text/plain', use_container_width=True)
            st.text_area("報告內容", value=st.session_state.report_texts.get('canceled_full', '無資料'), height=500, label_visibility="collapsed", key="text-canceled")
        else:
            st.info("沒有已取消的訂單。")
    # <<< CHANGE END >>>
