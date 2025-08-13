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
    # ... (此函數內容維持原樣，為節省版面省略)
    button_html = f"""
    <html><head><style>
        /* CSS styles */
    </style></head>
    <body>
        </body></html>
    """
    return components.html(button_html, height=45)

# =================================================================================
# 核心爬蟲邏輯 (已完整修復並整合)
# =================================================================================
class AutomationTool:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback

    def _update_status(self, message):
        if self.status_callback:
            self.status_callback(message)

    # --- WMS Driver & Methods (已從您的原始碼中完整恢復) ---
    def _initialize_wms_driver(self):
        chrome_options = Options()
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
                self._update_status(f"  > 未找到下一頁按鈕或翻頁失敗，抓取結束。")
                break
        self._update_status("  > 所有頁面資料抓取完畢。")
        return all_data

    def run_wms_scrape(self, url, username, password):
        driver = None
        try:
            driver = self._initialize_wms_driver()
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

    # --- NiceShoppy Driver & Methods (全新整合) ---
    def _initialize_shoppy_driver(self):
        self._update_status("  > 初始化蝦皮快手 WebDriver...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self._update_status("  > 配置「列印為PDF」功能...")
        settings = {
            "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
            "selectedDestinationId": "Save as PDF",
            "version": 2
        }
        prefs = {'printing.print_preview_sticky_settings.appState': json.dumps(settings)}
        options.add_experimental_option('prefs', prefs)
        options.add_argument('--kiosk-printing')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_window_size(1920, 1080)
        return driver

    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        driver = None
        try:
            driver = self._initialize_shoppy_driver()
            wait = WebDriverWait(driver, 20)
            
            self._update_status("  > 前往蝦皮快手登入頁面...")
            driver.get(url)
            login_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "登入")))
            login_link.click()
            email_input = wait.until(EC.visibility_of_element_located((By.ID, "username")))
            email_input.send_keys(username)
            password_input = driver.find_element(By.ID, "password")
            password_input.send_keys(password)
            submit_button = driver.find_element(By.NAME, "login")
            submit_button.click()
            self._update_status("✅ [成功] 蝦皮快手登入成功！")

            other_users_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "其他用戶")))
            other_users_link.click()
            self._update_status("  > 已切換至「其他用戶」頁籤。")

            self._update_status("  > 步驟 1: 掃描現有任務以獲取最大 Task ID...")
            existing_task_ids = set()
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                task_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in task_links:
                    try:
                        href = link.get_attribute('href')
                        if href and (match := re.search(r'task_id=(\d+)', href)):
                            existing_task_ids.add(int(match.group(1)))
                    except StaleElementReferenceException: continue
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height: break
                last_height = new_height
            max_existing_id = max(existing_task_ids) if existing_task_ids else 0
            self._update_status(f"  > 當前最大 Task ID 為: {max_existing_id}。")

            text_area = wait.until(EC.visibility_of_element_located((By.NAME, "unimart")))
            text_area.clear()
            text_area.send_keys(codes_to_process)
            self._update_status(f"  > 步驟 2: 已貼上 {len(codes_to_process.splitlines())} 筆代碼。")
            
            driver.find_element(By.XPATH, '//*[@id="shipping-list-submit-form"]/a[1]').click()
            self._update_status("  > 步驟 3: 已點擊『產出寄件單』。")

            self._update_status(f"  > 步驟 4: 等待大於 {max_existing_id} 的新任務生成...")
            long_wait = WebDriverWait(driver, 120)
            def find_new_task_with_scroll(driver):
                links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in links:
                    try:
                        if href := link.get_attribute('href'):
                            if match := re.search(r'task_id=(\d+)', href):
                                task_id = int(match.group(1))
                                if task_id > max_existing_id: return task_id
                    except StaleElementReferenceException: continue
                driver.execute_script("window.scrollBy(0, 500);")
                return False
            new_task_id = long_wait.until(find_new_task_with_scroll)
            self._update_status(f"  > ✅ 成功偵測到新任務！Task ID: {new_task_id}。")

            self._update_status(f"  > 步驟 5: 等待任務 {new_task_id} 按鈕變為可點擊...")
            print_button_xpath = f"//a[@class='btn btn-primary btn-sm' and contains(@href, 'task_id={new_task_id}')]"
            print_wait = WebDriverWait(driver, 300)
            latest_button = print_wait.until(EC.presence_of_element_located((By.XPATH, print_button_xpath)))
            self._update_status("  > ✅ 按鈕已啟用！準備點擊...")
            original_window = driver.current_window_handle
            driver.execute_script("arguments[0].click();", latest_button)
            
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
                    if page_text := page.extract_text():
                        full_text += page_text + "\n"
            
            self._update_status("  > 篩選物流條碼...")
            extracted_barcodes = re.findall(r'物流條碼：\s*(.{16})', full_text)
            st.session_state.shoppy_results = sorted(list(set(extracted_barcodes)))
            
            driver.close()
            driver.switch_to.window(original_window)
            return True

        except Exception as e:
            self._update_status(f"❌ 蝦皮快手處理過程中發生錯誤: {e}")
            if driver:
                error_path = 'shoppy_error.png'
                driver.save_screenshot(error_path)
                self._update_status(f"  > 錯誤畫面已截圖至 {error_path}")
            return False
        finally:
            if driver: driver.quit()

# =================================================================================
# Streamlit UI (已修改蝦皮快手分頁)
# =================================================================================
# (此部分維持和上次相同，為節省版面省略)
st.set_page_config(page_title="WMS & Shoppy 工具", page_icon="🚚", layout="wide")
# ... The rest of the Streamlit UI code goes here ...
# It includes the sidebar, the two main tabs, and the logic
# for buttons and displaying results.
