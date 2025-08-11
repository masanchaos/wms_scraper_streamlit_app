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
# 自訂的、零依賴的複製按鈕元件
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    escaped_text = html.escape(text_to_copy)
    button_html = f"""
    <html><head><style>.copy-btn {{ display: inline-block; padding: 6px 12px; margin-top: 5px; font-size: 14px; font-weight: 400; text-align: center; white-space: nowrap; vertical-align: middle; cursor: pointer; border: 1px solid #ccc; border-radius: 4px; color: #333; background-color: #fff; user-select: none; }}.copy-btn:hover {{ background-color: #f0f0f0; }}.copy-btn:active {{ background-color: #e6e6e6; border-color: #adadad; }}</style></head>
    <body><div id="text-for-{key}" style="display: none;">{escaped_text}</div><button id="{key}" class="copy-btn">{button_text}</button>
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
            picking_management_button = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath)))
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
        loading_spinner_xpath = "//div[contains(@class, 'j-loading')]"
        WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
        self._update_status("  > 資料已初步載入。")
        all_data = []
        page_count = 1
        item_list_container_xpath = "//div[contains(@class, 'list-items')]"
        while True:
            self._update_status(f"  > 正在抓取第 {page_count} 頁的資料...")
            # 優化：移除非必要的固定等待
            current_page_rows = driver.find_elements(By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]")
            if not current_page_rows:
                self._update_status("  > 未在頁面中找到任何資料列，抓取結束。")
                break
            for row in current_page_rows:
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
                if next_button.get_attribute('disabled'):
                    self._update_status("  > 「下一頁」按鈕已禁用，抓取結束。")
                    break
                else:
                    self._update_status(f"  > 第 {page_count} 頁抓取完畢，點擊下一頁...")
                    driver.execute_script("arguments[0].click();", next_button)
                    page_count += 1
                    self._update_status(f"  > 等待第 {page_count} 頁載入 (等待舊資料消失)...")
                    WebDriverWait(driver, 20).until(EC.staleness_of(current_page_rows[0]))
                    self._update_status(f"  > 等待第 {page_count} 頁載入 (等待新資料出現)...")
                    WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.XPATH, item_list_container_xpath)))
                    self._update_status(f"  > 第 {page_count} 頁載入成功。")
            except Exception:
                self._update_status("  > 未找到可點擊的「下一頁」按鈕，抓取結束。")
                break
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
            percentage = round((row['數量'] / total_count) * 100) if total_count > 0 else 0
            method_part = f"{row['寄送方式']}:"
            count_part = str(row['數量'])
            percent_part = f"({percentage}%)"
            line = f"{method_part:<{max_len}} {count_part:>6}   {percent_part:>6}"
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
    status_callback("  > 正在進行資料處理...")
    df['主要運送代碼'] = df['主要運送代碼'].astype(str)
    condition = (df['寄送方式'] == '7-11') & (df['主要運送代碼'].str.match(r'^\d', na=False))
    df.loc[condition, '寄送方式'] = '711大物流'
    status_callback("  > ✅ 細分組完成。")
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
    status_callback("✅ 資料處理完成，請查看下方報告。")

CREDENTIALS_FILE = "credentials.json"
def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}
    return {}
def save_credentials(username, password):
    with open(CREDENTIALS_FILE, 'w') as f: json.dump({"username": username, "password": password}, f)
def clear_credentials():
    if os.path.exists(CREDENTIALS_FILE): os.remove(CREDENTIALS_FILE)

# =================================================================================
# Streamlit 前端介面
# =================================================================================

st.set_page_config(page_title="WMS 資料擷取工具", page_icon="🚚", layout="wide")
if 'scraping_done' not in st.session_state: st.session_state.scraping_done = False
if 'final_df' not in st.session_state: st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state: st.session_state.df_filtered = pd.DataFrame()
if 'report_texts' not in st.session_state: st.session_state.report_texts = {}
with st.sidebar:
    st.image("https://www.jenjan.com.tw/images/logo.svg", width=200)
    st.header("⚙️ 連結與登入設定")
    saved_creds = load_credentials()
    saved_username = saved_creds.get("username", "")
    saved_password = saved_creds.get("password", "")
    url = st.text_input("目標網頁 URL", value="https://wms.jenjan.com.tw/")
    username = st.text_input("帳號", value=saved_username)
    password = st.text_input("密碼", value=saved_password, type="password")
    remember_me = st.checkbox("記住我 (下次自動填入帳密)")
    st.warning("⚠️ **安全性提醒**:\n勾選「記住我」會將帳密以可讀取的形式保存在伺服器上。僅在您信任此服務且帳號非高度敏感的情況下使用。")
st.title("🚚 WMS 網頁資料擷取工具")
st.markdown("---")
start_button = st.button("🚀 開始擷取資料", type="primary", use_container_width=True)
if start_button:
    if remember_me: save_credentials(username, password)
    else: clear_credentials()
    st.session_state.scraping_done = False
    status_area = st.empty()
    def streamlit_callback(message): status_area.info(message)
    with st.spinner("正在執行中，請勿關閉視窗..."):
        try:
            if not username or not password:
                status_area.error("❌ 請務必輸入帳號和密碼！")
            else:
                scraper = WmsScraper(url, username, password, status_callback=streamlit_callback)
                result_df = scraper.run()
                if not result_df.empty:
                    process_and_output_data(result_df, streamlit_callback)
                    st.session_state.scraping_done = True
                    status_area.success("🎉 所有任務完成！請查看下方的結果。")
                else:
                    status_area.warning("⚠️ 抓取完成，但沒有收到任何資料。")
        except Exception as e:
            st.session_state.scraping_done = False
            status_area.error(f"❌ 執行時發生致命錯誤：")
            st.exception(e)

if st.session_state.scraping_done:
    st.markdown("---")
    st.header("📊 擷取結果")
    
    # --- [最終 UI 設計] ---
    tab1, tab2 = st.tabs(["📊 指定項目報告", "📋 所有項目報告"])

    with tab1:
        st.subheader("指定項目統計與明細")
        st.text_area(
            "指定項目報告內容 (可直接複製)",
            value=st.session_state.report_texts.get('filtered_full', '無資料'),
            height=500,
            label_visibility="collapsed"
        )
        st.markdown("---")
        # 將操作按鈕整合進分頁中
        col1, col2 = st.columns(2)
        with col1:
            create_copy_button(st.session_state.report_texts.get('filtered_full', ''), "一鍵複製此報告", key="copy-btn-filtered")
        with col2:
            st.download_button(
                label="下載 CSV (僅指定項目)", 
                data=st.session_state.df_filtered.to_csv(index=False, encoding='utf-8-sig'),
                file_name=f"picking_data_FILTERED_{st.session_state.file_timestamp}.csv", 
                mime='text/csv', 
                use_container_width=True
            )

    with tab2:
        st.subheader("所有項目統計與明細")
        st.text_area(
            "所有項目報告內容 (可直接複製)",
            value=st.session_state.report_texts.get('all_full', '無資料'),
            height=500,
            label_visibility="collapsed"
        )
        st.markdown("---")
        # 將操作按鈕整合進分頁中
        col1, col2, col3 = st.columns(3)
        with col1:
            create_copy_button(st.session_state.report_texts.get('all_full', ''), "一鍵複製此報告", key="copy-btn-all")
        with col2:
            st.download_button(
                label="下載 CSV (所有資料)", 
                data=st.session_state.final_df.to_csv(index=False, encoding='utf-8-sig'),
                file_name=f"picking_data_ALL_{st.session_state.file_timestamp}.csv", 
                mime='text/csv', 
                use_container_width=True
            )
        with col3:
            st.download_button(
                label="下載 TXT (所有資料)", 
                data=st.session_state.report_texts.get('all_full', '').encode('utf-8'),
                file_name=f"picking_data_ALL_{st.session_state.file_timestamp}.txt", 
                mime='text/plain', 
                use_container_width=True
            )
