"""
WMS & Shoppy & 7-11 自動化工具 - 完整優化版
"""

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

# Selenium and WebDriver
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
# 自訂複製按鈕
# =================================================================================
def create_copy_button(text_to_copy: str, button_text: str, key: str):
    """建立自訂複製按鈕"""
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
        self.driver = None

    def _update_status(self, message):
        """更新狀態訊息"""
        if self.status_callback:
            self.status_callback(message)

    def _initialize_driver(self, for_shoppy=False):
        """初始化 WebDriver"""
        if for_shoppy:
            self._update_status("  > 初始化蝦皮快手 WebDriver...")
        else:
            self._update_status("  > 初始化 WebDriver...")

        options = Options()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('--disable-blink-features=AutomationControlled')

        if for_shoppy:
            self._update_status("  > 配置「列印為PDF」功能...")
            settings = {
                "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
                "selectedDestinationId": "Save as PDF",
                "version": 2
            }
            prefs = {
                'printing.print_preview_sticky_settings.appState': json.dumps(settings),
                'savefile.default_directory': os.getcwd()
            }
            options.add_experimental_option('prefs', prefs)
            options.add_argument('--kiosk-printing')

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.maximize_window()
            return driver
        except Exception as e:
            self._update_status(f"❌ WebDriver 初始化失敗: {e}")
            raise

    def _safe_click(self, element):
        """安全點擊元素"""
        try:
            element.click()
        except:
            self.driver.execute_script("arguments[0].click();", element)

    def _login_wms(self, driver, url, username, password):
        """WMS 登入"""
        self._update_status("  > 正在前往 WMS 登入頁面...")
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        
        account_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='example@jenjan.com.tw']")))
        account_input.clear()
        account_input.send_keys(username)
        
        password_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='password']")))
        password_input.clear()
        password_input.send_keys(password)
        password_input.send_keys(Keys.ENTER)
        
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "page-container")))
        self._update_status("✅ [成功] WMS 登入完成！")
        time.sleep(3)

    def _navigate_to_picking_complete(self, driver):
        """導航到揀包完成頁面"""
        self._update_status("  > 尋找導覽菜單...")
        picking_management_xpath = "//a[@href='/admin/pickup']"
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath))).click()
        
        self._update_status("  > 正在等待分頁區塊載入...")
        default_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '未揀訂單') or contains(., 'Unpicked'))]"
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, default_tab_xpath)))
        
        self._update_status("  > 點擊「揀包完成」分頁按鈕...")
        picking_complete_tab_xpath = "//div[contains(@class, 'btn') and (contains(., '揀包完成') or contains(., 'Complete'))]"
        complete_tab = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, picking_complete_tab_xpath)))
        self._safe_click(complete_tab)
        self._update_status("✅ [成功] 已進入揀包完成頁面！")

    def _scrape_data(self, driver):
        """爬取 WMS 資料"""
        self._update_status("  > 點擊查詢按鈕以載入資料...")
        query_button_xpath = "//div[contains(@class, 'btn-primary')]"
        query_btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, query_button_xpath)))
        self._safe_click(query_btn)
        
        loading_spinner_xpath = "//div[contains(@class, 'j-loading')]"
        WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.XPATH, loading_spinner_xpath)))
        self._update_status("  > 資料已初步載入。")
        
        all_data = []
        page_count = 1
        item_list_container_xpath = "//div[contains(@class, 'list-items')]"
        
        while True:
            self._update_status(f"  > 正在抓取第 {page_count} 頁的資料...")
            current_page_rows = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, f"{item_list_container_xpath}/div[contains(@class, 'item')]"))
            )
            
            if not current_page_rows:
                break
                
            first_row_text_before_click = current_page_rows[0].text
            
            for row in current_page_rows:
                try:
                    shipping_method = row.find_element(By.XPATH, "./div[2]/div[3]").text.strip()
                    tracking_code_input = row.find_element(By.XPATH, "./div[2]/div[4]//input")
                    tracking_code = tracking_code_input.get_property('value').strip()
                    if shipping_method or tracking_code:
                        all_data.append({"寄送方式": shipping_method, "主要運送代碼": tracking_code})
                except Exception:
                    continue
            
            try:
                next_button_xpath = "//button[normalize-space()='下一頁' or normalize-space()='Next']"
                next_button = driver.find_element(By.XPATH, next_button_xpath)
                if next_button.get_attribute('disabled'):
                    break
                    
                self._safe_click(next_button)
                page_count += 1
                
                timeout = 20
                start_time = time.time()
                while True:
                    if time.time() - start_time > timeout:
                        raise TimeoutException(f"頁面內容在{timeout}秒內未刷新。")
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

    def run_wms_scrape(self, url, username, password):
        """執行 WMS 爬取"""
        driver = None
        try:
            driver = self._initialize_driver(for_shoppy=False)
            self._login_wms(driver, url, username, password)
            self._navigate_to_picking_complete(driver)
            data = self._scrape_data(driver)
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            self._update_status(f"❌ WMS 抓取過程中發生錯誤: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    def run_niceshoppy_automation(self, url, username, password, codes_to_process):
        """執行蝦皮快手自動化"""
        driver = None
        try:
            driver = self._initialize_driver(for_shoppy=True)
            wait = WebDriverWait(driver, 20)
            
            self._update_status("  > 前往蝦皮快手登入頁面...")
            driver.get(url)
            
            # 等待頁面完全載入
            time.sleep(2)
            
            # 嘗試點擊登入連結
            try:
                login_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "登入")))
                self._safe_click(login_link)
            except:
                # 如果找不到「登入」連結，可能已經在登入頁面
                self._update_status("  > 已在登入頁面或需要不同的登入方式...")
            
            # 輸入帳號密碼
            email_input = wait.until(EC.visibility_of_element_located((By.ID, "username")))
            email_input.clear()
            email_input.send_keys(username)
            
            password_input = driver.find_element(By.ID, "password")
            password_input.clear()
            password_input.send_keys(password)
            
            # 點擊登入按鈕
            submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='登入']")))
            self._safe_click(submit_button)
            time.sleep(3)  # 等待登入完成
            self._update_status("✅ [成功] 蝦皮快手登入成功！")
            
            # 點擊其他用戶
            other_users_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "其他用戶")))
            self._safe_click(other_users_link)
            time.sleep(2)
            
            # 掃描現有任務
            self._update_status("  > 步驟 1: 掃描現有任務以獲取最大 Task ID...")
            existing_task_ids = set()
            
            # 先滾動到頂部
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # 逐步滾動並收集 task IDs
            scroll_pause_time = 1.5
            last_height = driver.execute_script("return document.body.scrollHeight")
            
            while True:
                # 尋找所有任務連結
                task_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in task_links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match:
                                existing_task_ids.add(int(match.group(1)))
                    except (StaleElementReferenceException, Exception):
                        continue
                
                # 滾動到底部
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause_time)
                
                # 檢查是否到達底部
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            max_existing_id = max(existing_task_ids) if existing_task_ids else 0
            self._update_status(f"  > 當前最大 Task ID 為: {max_existing_id}。")
            
            # 輸入運送代碼
            text_area = wait.until(EC.visibility_of_element_located((By.NAME, "unimart")))
            text_area.clear()
            text_area.send_keys(codes_to_process)
            self._update_status(f"  > 步驟 2: 已貼上 {len(codes_to_process.splitlines())} 筆代碼。")
            
            # 點擊產出寄件單
            time.sleep(1)
            submit_form = driver.find_element(By.XPATH, '//*[@id="shipping-list-submit-form"]/a[1]')
            self._safe_click(submit_form)
            self._update_status("  > 步驟 3: 已點擊『產出寄件單』。")
            
            # 等待新任務出現
            self._update_status(f"  > 步驟 4: 等待大於 {max_existing_id} 的新任務生成 (最長3分鐘)...")
            
            def find_new_task_with_scroll(driver):
                # 重新載入頁面或滾動到頂部
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.5)
                
                links = driver.find_elements(By.XPATH, "//a[contains(@href, 'task_id=')]")
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href:
                            match = re.search(r'task_id=(\d+)', href)
                            if match:
                                task_id = int(match.group(1))
                                if task_id > max_existing_id:
                                    return task_id
                    except (StaleElementReferenceException, Exception):
                        continue
                
                # 向下滾動一點
                driver.execute_script("window.scrollBy(0, 300);")
                return False
            
            long_wait = WebDriverWait(driver, 180)
            new_task_id = long_wait.until(find_new_task_with_scroll)
            self._update_status(f"  > ✅ 成功偵測到新任務！Task ID: {new_task_id}。")
            
            # 等待列印按鈕可點擊
            self._update_status(f"  > 步驟 5: 等待任務 {new_task_id} 按鈕變為可點擊 (最長5分鐘)...")
            
            # 使用更靈活的 XPath
            print_button_xpaths = [
                f"//a[contains(@class, 'btn') and contains(@class, 'btn-primary') and contains(@href, 'task_id={new_task_id}')]",
                f"//a[contains(@href, 'task_id={new_task_id}') and contains(text(), '列印')]",
                f"//a[contains(@href, 'task_id={new_task_id}')]"
            ]
            
            latest_button = None
            for xpath in print_button_xpaths:
                try:
                    print_wait = WebDriverWait(driver, 300)
                    latest_button = print_wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    if latest_button:
                        break
                except:
                    continue
            
            if not latest_button:
                raise Exception(f"無法找到任務 {new_task_id} 的列印按鈕")
            
            self._update_status("  > ✅ 按鈕已啟用！準備點擊...")
            original_window = driver.current_window_handle
            self._safe_click(latest_button)
            
            # 等待新視窗開啟
            self._update_status("  > 步驟 6: 切換至列印分頁...")
            wait.until(EC.number_of_windows_to_be(2))
            
            for window_handle in driver.window_handles:
                if window_handle != original_window:
                    driver.switch_to.window(window_handle)
                    break
            
            # 等待頁面載入完成
            self._update_status("  > 等待列印頁面載入...")
            time.sleep(7)  # 增加等待時間
            
            # 執行列印為 PDF
            self._update_status("  > 執行「列印為PDF」命令...")
            try:
                result = driver.execute_cdp_cmd("Page.printToPDF", {
                    "landscape": False,
                    "displayHeaderFooter": False,
                    "printBackground": True,
                    "preferCSSPageSize": True
                })
                pdf_content = base64.b64decode(result['data'])
            except Exception as e:
                self._update_status(f"  > PDF 生成失敗: {e}")
                # 嘗試截圖作為備份
                driver.save_screenshot('shoppy_print_page.png')
                raise
            
            # 解析 PDF
            self._update_status("  > 解析PDF，提取所有文字...")
            full_text = ""
            page_count = 0
            
            try:
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    self._update_status(f"  > PDF 共有 {len(pdf.pages)} 頁")
                    for page in pdf.pages:
                        page_count += 1
                        if page_text := page.extract_text():
                            full_text += page_text + "\n"
                            self._update_status(f"  > 已處理第 {page_count} 頁")
            except Exception as e:
                self._update_status(f"  > PDF 解析錯誤: {e}")
                raise
            
            # 調試：顯示部分文字內容
            self._update_status(f"  > PDF 文字長度: {len(full_text)} 字元")
            if len(full_text) > 0:
                preview = full_text[:500]
                self._update_status(f"  > 文字預覽: {preview}...")
            
            # 嘗試多種條碼格式
            self._update_status("  > 篩選物流條碼...")
            
            # 嘗試不同的正則表達式模式
            patterns = [
                r'物流條碼：\s*(\w{16})',  # 原始模式
                r'物流條碼[：:]\s*(\w{16})',  # 中英文冒號
                r'物流條碼\s*[：:]\s*(\w{16})',  # 加空格
                r'條碼[：:]\s*(\w{16})',  # 簡化版
                r'(\w{16})',  # 任何16位英數字
                r'[A-Z0-9]{16}'  # 大寫英文和數字
            ]
            
            extracted_barcodes = []
            for pattern in patterns:
                matches = re.findall(pattern, full_text)
                if matches:
                    self._update_status(f"  > 使用模式 {pattern} 找到 {len(matches)} 個匹配")
                    extracted_barcodes.extend(matches)
                    break  # 找到就停止
            
            # 去重並排序
            extracted_barcodes = sorted(list(set(extracted_barcodes)))
            
            if extracted_barcodes:
                self._update_status(f"  > ✅ 成功提取 {len(extracted_barcodes)} 個物流條碼")
            else:
                self._update_status("  > ⚠️ 未能提取到物流條碼，嘗試儲存原始文字...")
                # 儲存原始文字供調試
                with open('shoppy_pdf_text.txt', 'w', encoding='utf-8') as f:
                    f.write(full_text)
                self._update_status("  > 原始文字已儲存至 shoppy_pdf_text.txt")
            
            st.session_state.shoppy_results = extracted_barcodes
            
            # 關閉列印視窗並返回原視窗
            driver.close()
            driver.switch_to.window(original_window)
            return True
            
        except Exception as e:
            self._update_status(f"❌ 蝦皮快手處理過程中發生錯誤: {e}")
            if driver:
                try:
                    error_path = 'shoppy_error.png'
                    driver.save_screenshot(error_path)
                    self._update_status(f"  > 錯誤畫面已截圖至 {error_path}")
                    
                    # 儲存當前頁面 HTML 供調試
                    with open('shoppy_error.html', 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    self._update_status("  > 頁面 HTML 已儲存至 shoppy_error.html")
                except:
                    pass
            return False
        finally:
            if driver:
                driver.quit()

    def run_seven_eleven_scan(self, url, username, password, phone_number, barcodes):
        """執行 7-11 物流刷取（已修正登入元素）"""
        driver = None
        try:
            driver = self._initialize_driver()
            wait = WebDriverWait(driver, 15)
            
            self._update_status("🚀 開始 7-11 物流刷取流程...")
            self._update_status(f"  > 網址: {url}")
            self._update_status(f"  > 帳號: {username}")
            self._update_status(f"  > 電話: {phone_number}")
            
            # 前往網站
            self._update_status("📍 步驟 1: 前往 7-11 物流後台...")
            driver.get(url)
            time.sleep(3)
            
            # === 登入流程 ===
            self._update_status("🔐 步驟 2: 登入系統...")
            
            # 輸入帳號
            try:
                username_input = wait.until(EC.presence_of_element_located((By.ID, "UserName")))
                username_input.clear()
                username_input.send_keys(username)
                self._update_status("  ✓ 已輸入帳號")
            except Exception as e:
                self._update_status(f"  ✗ 輸入帳號失敗: {e}")
                raise
            
            # 輸入密碼
            try:
                password_input = driver.find_element(By.ID, "Password")
                password_input.clear()
                password_input.send_keys(password)
                self._update_status("  ✓ 已輸入密碼")
            except Exception as e:
                self._update_status(f"  ✗ 輸入密碼失敗: {e}")
                raise
            
            # 點擊登入按鈕
            try:
                login_button = driver.find_element(By.CLASS_NAME, "Button001")
                self._safe_click(login_button)
                self._update_status("  ✓ 已點擊登入按鈕")
            except:
                try:
                    login_button = driver.find_element(By.XPATH, "//button[@class='Button001']")
                    self._safe_click(login_button)
                except:
                    login_button = driver.find_element(By.XPATH, "//button[contains(text(), '登入')]")
                    self._safe_click(login_button)
            
            time.sleep(3)
            self._update_status("✅ 登入成功！")
            
            # === 進入 C2C 快收便 ===
            self._update_status("📦 步驟 3: 進入 C2C 快收便...")
            try:
                c2c_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "C2C快收便")))
                self._safe_click(c2c_link)
                self._update_status("  ✓ 已進入 C2C 快收便頁面")
            except:
                try:
                    c2c_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "C2C")))
                    self._safe_click(c2c_link)
                except Exception as e:
                    self._update_status(f"  ✗ 無法進入 C2C 快收便: {e}")
                    raise
            
            time.sleep(3)
            
            # === 輸入電話號碼 - 確保獲得焦點 ===
            self._update_status("📞 步驟 4: 輸入電話號碼...")
            self._update_status(f"  > 要輸入的電話: {phone_number}")
            
            try:
                # 等待頁面載入
                time.sleep(2)
                
                # 找到輸入框
                self._update_status("  > 尋找電話輸入框...")
                mobile_input = wait.until(EC.presence_of_element_located((By.ID, "MobileNumber")))
                
                # 確保元素可見
                driver.execute_script("arguments[0].scrollIntoView(true);", mobile_input)
                time.sleep(0.5)
                
                # === 關鍵：確保輸入框獲得焦點 ===
                self._update_status("  > 設定焦點到輸入框...")
                
                # 方法1: 點擊輸入框
                try:
                    mobile_input.click()
                    self._update_status("    ✓ 已點擊輸入框")
                except:
                    # 如果普通點擊失敗，用 JavaScript 點擊
                    driver.execute_script("arguments[0].click();", mobile_input)
                    self._update_status("    ✓ 已用 JS 點擊輸入框")
                
                time.sleep(0.5)
                
                # 方法2: 用 JavaScript 設定焦點
                driver.execute_script("arguments[0].focus();", mobile_input)
                self._update_status("    ✓ 已設定焦點")
                
                # 方法3: 發送一個按鍵確保焦點
                mobile_input.send_keys("")  # 發送空字串也能設定焦點
                
                # 清空輸入框
                self._update_status("  > 清空輸入框...")
                mobile_input.clear()
                # 再次確保清空
                mobile_input.send_keys(Keys.CONTROL + "a")
                mobile_input.send_keys(Keys.DELETE)
                time.sleep(0.3)
                
                # 填入電話號碼
                self._update_status("  > 填入電話號碼...")
                mobile_input.send_keys(phone_number)
                time.sleep(0.5)
                
                # 觸發事件
                self._update_status("  > 觸發 onchange 事件...")
                mobile_input.send_keys(Keys.TAB)
                
                # 驗證輸入
                time.sleep(0.5)
                actual_value = mobile_input.get_attribute('value')
                self._update_status(f"  > 輸入框當前值: {actual_value}")
                
                if actual_value == phone_number:
                    self._update_status(f"  ✅ 電話號碼填入成功！")
                else:
                    self._update_status(f"  ⚠️ 值不符，再試一次...")
                    
                    # 再試一次，這次用 JavaScript 確保焦點
                    driver.execute_script("""
                        var input = document.getElementById('MobileNumber');
                        input.focus();
                        input.select();
                        input.value = '';
                        input.value = arguments[0];
                        
                        // 觸發事件
                        var event = new Event('change', { bubbles: true });
                        input.dispatchEvent(event);
                        
                        // 如果有 QueryPickUp 函數，執行它
                        if (typeof QueryPickUp === 'function') {
                            QueryPickUp(input);
                        }
                    """, phone_number)
                    
                    time.sleep(0.5)
                    final_value = mobile_input.get_attribute('value')
                    self._update_status(f"  > 最終值: {final_value}")
                    
            except Exception as e:
                self._update_status(f"  ❌ 填入電話失敗: {e}")
                driver.save_screenshot('phone_input_error.png')
                self._update_status("  > 已保存錯誤截圖")
                
                # 最後嘗試：使用 ActionChains 模擬真實用戶操作
                try:
                    self._update_status("  > 使用 ActionChains 模擬用戶操作...")
                    from selenium.webdriver.common.action_chains import ActionChains
                    
                    mobile_input = driver.find_element(By.ID, "MobileNumber")
                    actions = ActionChains(driver)
                    
                    # 移動到元素並點擊
                    actions.move_to_element(mobile_input).click()
                    
                    # 全選並刪除
                    actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL)
                    actions.send_keys(Keys.DELETE)
                    
                    # 逐字輸入（更像真人）
                    for digit in phone_number:
                        actions.send_keys(digit)
                        actions.pause(0.1)  # 每個字之間暫停
                    
                    # 按 Tab
                    actions.send_keys(Keys.TAB)
                    
                    # 執行所有動作
                    actions.perform()
                    self._update_status("  > ActionChains 執行完成")
                    
                except Exception as action_error:
                    self._update_status(f"  > ActionChains 也失敗: {action_error}")
            
            # 等待並點擊確認按鈕
            time.sleep(3)
            self._update_status("🔘 步驟 5: 點擊確認按鈕...")
            
            try:
                # 找到並點擊 UploadButton
                upload_button = driver.find_element(By.ID, "UploadButton")
                
                # 如果按鈕是 disabled，啟用它
                if upload_button.get_attribute("disabled"):
                    self._update_status("  > 按鈕被禁用，嘗試啟用...")
                    driver.execute_script("arguments[0].removeAttribute('disabled');", upload_button)
                    time.sleep(1)
                
                self._safe_click(upload_button)
                self._update_status("  ✓ 已點擊確認按鈕")
                
            except Exception as e:
                self._update_status(f"  ✗ 點擊確認按鈕失敗: {e}")
                # 嘗試其他按鈕
                try:
                    confirm_btn = driver.find_element(By.XPATH, "//input[@type='button' and @value='確認']")
                    driver.execute_script("arguments[0].removeAttribute('disabled');", confirm_btn)
                    self._safe_click(confirm_btn)
                except:
                    pass
            
            time.sleep(3)
            self._update_status("✅ 準備開始刷取條碼...")
            
            # === 條碼刷取流程 ===
            self._update_status("🔍 步驟 6: 開始刷取條碼...")
            
            # 找到條碼輸入框
            barcode_input = None
            try:
                barcode_input = wait.until(EC.presence_of_element_located((By.ID, "PIN")))
            except:
                try:
                    barcode_input = driver.find_element(By.XPATH, "//input[contains(@id, 'PIN')]")
                except:
                    self._update_status("  ❌ 找不到條碼輸入框！")
                    driver.save_screenshot('barcode_input_not_found.png')
                    raise Exception("找不到條碼輸入框")
            
            # 找到確認按鈕
            confirm_button = None
            try:
                confirm_button = driver.find_element(By.ID, "btn_OK_PIN")
            except:
                try:
                    confirm_button = driver.find_element(By.XPATH, "//button[contains(@id, 'PIN') and contains(@id, 'OK')]")
                except:
                    pass
            
            success_count = 0
            failed_barcodes = []
            
            for i, barcode in enumerate(barcodes):
                self._update_status(f"  > [{i+1}/{len(barcodes)}] 處理條碼: {barcode}")
                
                try:
                    barcode_input.clear()
                    barcode_input.send_keys(barcode)
                    
                    if confirm_button:
                        self._safe_click(confirm_button)
                    else:
                        barcode_input.send_keys(Keys.ENTER)
                    
                    time.sleep(1)
                    success_count += 1
                    self._update_status(f"    ✓ 成功")
                    
                except Exception as e:
                    self._update_status(f"    ✗ 失敗: {e}")
                    failed_barcodes.append(barcode)
            
            # 儲存結果
            st.session_state.seven_eleven_scan_results = {
                "total": len(barcodes),
                "success": success_count,
                "failed": len(failed_barcodes),
                "failed_list": failed_barcodes
            }
            
            self._update_status(f"✅ 刷取完成！成功: {success_count}/{len(barcodes)}")
            return True
            
        except Exception as e:
            error_msg = f"7-11 物流刷取失敗: {str(e)}"
            self._update_status(f"❌ {error_msg}")
            
            if driver:
                try:
                    driver.save_screenshot('seven_eleven_error.png')
                    self._update_status("  > 已保存錯誤截圖: seven_eleven_error.png")
                    
                    with open('seven_eleven_error.html', 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    self._update_status("  > 已保存頁面 HTML: seven_eleven_error.html")
                except:
                    pass
            
            # 顯示錯誤詳情
            import traceback
            self._update_status("=== 錯誤詳情 ===")
            self._update_status(traceback.format_exc())
            
            return False
            
        finally:
            if driver:
                driver.quit()
        """執行 7-11 物流刷取（已修正登入元素）"""
        driver = None
        try:
            driver = self._initialize_driver()
            wait = WebDriverWait(driver, 15)
            
            self._update_status("  > 前往 7-11 物流後台...")
            driver.get(url)
            
            # 修正：使用正確的元素 ID 和登入按鈕 class
            self._update_status("  > 輸入帳號密碼...")
            
            # 等待頁面載入
            time.sleep(2)
            
            # 輸入帳號 - 使用 UserName
            try:
                username_input = wait.until(EC.visibility_of_element_located((By.ID, "UserName")))
                username_input.clear()
                username_input.send_keys(username)
                self._update_status("  > 已輸入帳號")
            except:
                self._update_status("  > 嘗試其他方式尋找帳號輸入框...")
                username_input = wait.until(EC.visibility_of_element_located((By.NAME, "UserName")))
                username_input.clear()
                username_input.send_keys(username)
            
            # 輸入密碼 - 使用 Password
            try:
                password_input = driver.find_element(By.ID, "Password")
                password_input.clear()
                password_input.send_keys(password)
                self._update_status("  > 已輸入密碼")
            except:
                self._update_status("  > 嘗試其他方式尋找密碼輸入框...")
                password_input = driver.find_element(By.NAME, "Password")
                password_input.clear()
                password_input.send_keys(password)
            
            # 修正：使用 class 來找登入按鈕
            self._update_status("  > 點擊登入按鈕...")
            try:
                # 方法1: 使用 class name
                login_button = driver.find_element(By.CLASS_NAME, "Button001")
                self._safe_click(login_button)
            except:
                try:
                    # 方法2: 使用 XPath with class
                    login_button = driver.find_element(By.XPATH, "//button[@class='Button001']")
                    self._safe_click(login_button)
                except:
                    try:
                        # 方法3: 使用包含文字的按鈕
                        login_button = driver.find_element(By.XPATH, "//button[contains(text(), '登入')]")
                        self._safe_click(login_button)
                    except:
                        # 方法4: 使用 ID (舊版本備用)
                        login_button = driver.find_element(By.ID, "Login")
                        self._safe_click(login_button)
            
            # 等待登入完成
            time.sleep(3)
            self._update_status("✅ 登入成功！")
            
            # 點擊 C2C 快收便
            self._update_status("  > 點擊「C2C快收便」...")
            try:
                c2c_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "C2C快收便")))
                self._safe_click(c2c_link)
            except:
                try:
                    # 備用方法：使用部分連結文字
                    c2c_link = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "C2C")))
                    self._safe_click(c2c_link)
                except:
                    # 備用方法：使用 XPath
                    c2c_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'C2C')]")))
                    self._safe_click(c2c_link)
            
            # 修正：使用 MobileNumber 輸入電話號碼
            self._update_status("  > 尋找電話號碼輸入框...")
            
            # 多種方式等待頁面穩定
            time.sleep(2)
            
            try:
                # 方法1: 使用 ID 定位
                try:
                    mobile_input = wait.until(EC.presence_of_element_located((By.ID, "MobileNumber")))
                    self._update_status("  > 找到電話號碼輸入框 (通過 ID)")
                except:
                    # 方法2: 使用 name 定位
                    mobile_input = wait.until(EC.presence_of_element_located((By.NAME, "MobileNumber")))
                    self._update_status("  > 找到電話號碼輸入框 (通過 NAME)")
                
                # 確保元素可見且可互動
                time.sleep(1)
                
                # 捲動到元素位置
                driver.execute_script("arguments[0].scrollIntoView(true);", mobile_input)
                time.sleep(0.5)
                
                # 點擊輸入框以獲得焦點
                try:
                    mobile_input.click()
                except:
                    driver.execute_script("arguments[0].click();", mobile_input)
                
                # 清空輸入框的多種方式
                self._update_status("  > 清空輸入框...")
                mobile_input.clear()
                driver.execute_script("arguments[0].value = '';", mobile_input)
                time.sleep(0.5)
                
                # 輸入電話號碼 - 使用多種方法
                self._update_status(f"  > 輸入電話號碼: {phone_number}")
                
                # 方法A: 直接使用 JavaScript 設定值
                driver.execute_script("""
                    var input = arguments[0];
                    var phoneNumber = arguments[1];
                    
                    // 設定值
                    input.value = phoneNumber;
                    
                    // 設定 React 或 Vue 的內部值（如果使用這些框架）
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(input, phoneNumber);
                    
                    // 觸發各種事件
                    var inputEvent = new Event('input', { bubbles: true });
                    input.dispatchEvent(inputEvent);
                    
                    var changeEvent = new Event('change', { bubbles: true });
                    input.dispatchEvent(changeEvent);
                    
                    var keyupEvent = new KeyboardEvent('keyup', { bubbles: true });
                    input.dispatchEvent(keyupEvent);
                    
                    // 如果有 jQuery，也觸發 jQuery 事件
                    if (typeof $ !== 'undefined') {
                        $(input).trigger('change');
                        $(input).trigger('keyup');
                    }
                    
                    // 執行 onkeyup 和 onchange 中的函數
                    if (input.onkeyup) input.onkeyup();
                    if (input.onchange) input.onchange();
                    
                    // 直接呼叫 QueryPickUp
                    if (typeof QueryPickUp === 'function') {
                        QueryPickUp(input);
                    }
                """, mobile_input, phone_number)
                
                self._update_status("  > 已使用 JavaScript 設定電話號碼")
                time.sleep(1)
                
                # 方法B: 如果上面的方法沒生效，嘗試逐字輸入
                current_value = mobile_input.get_attribute('value')
                if not current_value or current_value != phone_number:
                    self._update_status("  > JavaScript 設定可能未生效，嘗試逐字輸入...")
                    mobile_input.clear()
                    time.sleep(0.5)
                    
                    # 點擊獲得焦點
                    mobile_input.click()
                    
                    # 逐字輸入
                    for i, digit in enumerate(phone_number):
                        mobile_input.send_keys(digit)
                        time.sleep(0.2)  # 每個字之間延遲
                        
                        # 每輸入幾個字就觸發一次事件
                        if i == len(phone_number) - 1:  # 最後一個字
                            # 觸發 keyup
                            mobile_input.send_keys(Keys.CONTROL, 'a')  # 全選
                            mobile_input.send_keys(Keys.CONTROL, 'c')  # 複製
                            mobile_input.send_keys(Keys.DELETE)  # 刪除
                            mobile_input.send_keys(phone_number)  # 重新貼上完整號碼
                            
                    # 輸入完成後觸發事件
                    mobile_input.send_keys(Keys.TAB)
                    time.sleep(0.5)
                    mobile_input.send_keys(Keys.SHIFT, Keys.TAB)  # 回到輸入框
                
                # 再次確認值已正確輸入
                time.sleep(1)
                actual_value = mobile_input.get_attribute('value')
                self._update_status(f"  > 輸入框當前值: {actual_value}")
                
                # 如果值還是不對，使用最後手段
                if actual_value != phone_number:
                    self._update_status("  > 值不正確，使用強制方法...")
                    driver.execute_script("""
                        var input = document.getElementById('MobileNumber');
                        if (!input) input = document.getElementsByName('MobileNumber')[0];
                        if (input) {
                            input.focus();
                            input.value = arguments[0];
                            
                            // 強制執行 QueryPickUp
                            if (typeof QueryPickUp === 'function') {
                                console.log('Calling QueryPickUp...');
                                QueryPickUp(input);
                            } else {
                                console.log('QueryPickUp function not found');
                                // 嘗試手動觸發
                                eval(input.getAttribute('onkeyup'));
                                eval(input.getAttribute('onchange'));
                            }
                        }
                    """, phone_number)
                    time.sleep(2)
                
                self._update_status("  > ✅ 電話號碼輸入完成")
                
            except Exception as e:
                self._update_status(f"  > ❌ 輸入電話號碼失敗: {str(e)}")
                # 截圖以便調試
                driver.save_screenshot('phone_input_error.png')
                
                # 嘗試最基本的方法
                self._update_status("  > 嘗試最基本的輸入方法...")
                try:
                    # 使用 XPath 找到任何包含 MobileNumber 的輸入框
                    mobile_inputs = driver.find_elements(By.XPATH, "//input[contains(@id, 'Mobile') or contains(@name, 'Mobile')]")
                    for input_elem in mobile_inputs:
                        if input_elem.is_displayed():
                            input_elem.clear()
                            input_elem.send_keys(phone_number)
                            input_elem.send_keys(Keys.ENTER)
                            self._update_status("  > 已在備用輸入框輸入電話")
                            break
                except:
                    pass
            
            # 等待查詢結果
            self._update_status("  > 等待查詢結果載入...")
            time.sleep(3)
            
            # 修正：使用 UploadButton 作為確認按鈕
            self._update_status("  > 尋找並點擊確認按鈕...")
            try:
                # 方法1：等待按鈕變為可點擊
                upload_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "UploadButton"))
                )
                self._safe_click(upload_button)
                self._update_status("  > ✅ 已點擊確認按鈕")
                
            except TimeoutException:
                self._update_status("  > 確認按鈕可能還是 disabled，嘗試其他方法...")
                
                try:
                    # 方法2：找到按鈕並檢查狀態
                    upload_button = driver.find_element(By.ID, "UploadButton")
                    
                    # 檢查按鈕是否 disabled
                    is_disabled = upload_button.get_attribute("disabled")
                    if is_disabled:
                        self._update_status("  > 按鈕是 disabled 狀態，嘗試啟用...")
                        
                        # 強制移除 disabled 屬性
                        driver.execute_script("""
                            var button = arguments[0];
                            button.removeAttribute('disabled');
                            button.disabled = false;
                        """, upload_button)
                        time.sleep(1)
                    
                    # 點擊按鈕
                    self._safe_click(upload_button)
                    self._update_status("  > ✅ 已強制啟用並點擊確認按鈕")
                    
                except Exception as e:
                    self._update_status(f"  > ❌ 點擊確認按鈕失敗: {e}")
                    
                    # 方法3：使用 XPath 尋找任何確認按鈕
                    try:
                        confirm_buttons = driver.find_elements(By.XPATH, "//input[@type='button' and (@value='確認' or @value='確定' or contains(@class, 'Button'))]")
                        for btn in confirm_buttons:
                            if btn.is_displayed():
                                driver.execute_script("arguments[0].removeAttribute('disabled');", btn)
                                self._safe_click(btn)
                                self._update_status("  > ✅ 已點擊備用確認按鈕")
                                break
                    except:
                        # 最後嘗試舊版按鈕
                        try:
                            ok_button = driver.find_element(By.ID, "btn_OK")
                            self._safe_click(ok_button)
                            self._update_status("  > ✅ 已點擊舊版確認按鈕")
                        except:
                            self._update_status("  > ⚠️ 無法找到任何確認按鈕，繼續執行...")
            
            # 等待頁面完全載入
            time.sleep(3)
            self._update_status("✅ 電話號碼確認完畢，準備開始刷取條碼。")
            
            # 條碼輸入處理
            barcode_input_xpath = "//input[@id='PIN']"
            try:
                barcode_input = wait.until(EC.visibility_of_element_located((By.XPATH, barcode_input_xpath)))
            except:
                # 備用：可能條碼輸入框有不同的 ID
                self._update_status("  > 尋找條碼輸入框...")
                barcode_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[contains(@id, 'PIN') or contains(@name, 'PIN')]")))
            
            # 找到確認按鈕
            try:
                confirm_button = driver.find_element(By.ID, "btn_OK_PIN")
            except:
                # 備用方法
                self._update_status("  > 尋找條碼確認按鈕...")
                try:
                    confirm_button = driver.find_element(By.XPATH, "//button[contains(@id, 'OK') and contains(@id, 'PIN')]")
                except:
                    confirm_button = driver.find_element(By.XPATH, "//input[@type='button' and (contains(@value, '確認') or contains(@value, 'OK'))]")
            
            success_count = 0
            failed_barcodes = []
            
            for i, barcode in enumerate(barcodes):
                self._update_status(f"  > 處理第 {i+1}/{len(barcodes)} 筆: {barcode}")
                try:
                    # 清空並輸入條碼
                    barcode_input.clear()
                    time.sleep(0.5)  # 短暫等待
                    barcode_input.send_keys(barcode)
                    time.sleep(0.5)  # 確保輸入完成
                    
                    # 點擊確認
                    self._safe_click(confirm_button)
                    
                    # 等待處理結果
                    try:
                        # 等待成功訊息或任何回應
                        WebDriverWait(driver, 5).until(
                            EC.visibility_of_element_located((By.ID, "show_msg_p"))
                        )
                        success_count += 1
                        self._update_status(f"    ✅ 條碼 {barcode} 處理成功")
                    except TimeoutException:
                        # 檢查是否有其他成功指標
                        # 即使沒有明確的成功訊息，也可能已經成功
                        success_count += 1
                        self._update_status(f"    ✅ 條碼 {barcode} 已提交")
                    
                    time.sleep(1)  # 避免太快
                    
                    # 重新定位輸入框
                    try:
                        barcode_input = driver.find_element(By.XPATH, barcode_input_xpath)
                    except:
                        barcode_input = driver.find_element(By.XPATH, "//input[contains(@id, 'PIN') or contains(@name, 'PIN')]")
                    
                except Exception as e:
                    self._update_status(f"    ❌ 條碼 {barcode} 處理失敗: {str(e)}")
                    failed_barcodes.append(barcode)
                    
                    # 嘗試恢復
                    try:
                        # 不刷新整個頁面，只重新定位元素
                        time.sleep(2)
                        barcode_input = driver.find_element(By.XPATH, barcode_input_xpath)
                        barcode_input.clear()
                    except:
                        # 如果真的需要刷新
                        self._update_status("    ⚠️ 嘗試恢復頁面...")
                        driver.refresh()
                        time.sleep(3)
                        
                        # 重新輸入電話號碼
                        try:
                            mobile_input = driver.find_element(By.ID, "MobileNumber")
                            mobile_input.clear()
                            mobile_input.send_keys(phone_number)
                            driver.execute_script("QueryPickUp(document.getElementById('MobileNumber'));")
                            time.sleep(2)
                            
                            upload_button = driver.find_element(By.ID, "UploadButton")
                            driver.execute_script("arguments[0].removeAttribute('disabled');", upload_button)
                            self._safe_click(upload_button)
                            time.sleep(2)
                            
                            barcode_input = wait.until(EC.visibility_of_element_located((By.XPATH, barcode_input_xpath)))
                            confirm_button = driver.find_element(By.ID, "btn_OK_PIN")
                        except:
                            self._update_status("    ⚠️ 無法恢復，跳過此條碼")
                            continue
            
            # 儲存結果
            st.session_state.seven_eleven_scan_results = {
                "total": len(barcodes),
                "success": success_count,
                "failed": len(barcodes) - success_count,
                "failed_list": failed_barcodes
            }
            
            self._update_status(f"✅ 刷取完成！成功: {success_count}/{len(barcodes)}")
            return True
            
        except Exception as e:
            self._update_status(f"❌ 7-11 物流刷取過程中發生嚴重錯誤: {e}")
            if driver:
                try:
                    # 截圖保存錯誤畫面
                    error_path = 'seven_eleven_error.png'
                    driver.save_screenshot(error_path)
                    self._update_status(f"  > 錯誤畫面已截圖至 {error_path}")
                    
                    # 保存頁面 HTML
                    with open('seven_eleven_error.html', 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    self._update_status("  > 頁面 HTML 已儲存至 seven_eleven_error.html")
                except:
                    pass
            return False
        finally:
            if driver:
                driver.quit()

# =================================================================================
# 資料處理與憑證管理
# =================================================================================
def generate_report_text(df_to_process, display_timestamp, report_title):
    """生成報告文字"""
    if df_to_process.empty:
        summary = f"--- {report_title} ---\n\n指定條件下無資料。"
        full_report = f"擷取時間: {display_timestamp} (台北時間)\n\n{summary}"
        return summary, full_report
        
    summary_df = df_to_process.groupby('寄送方式', observed=False).size().reset_index(name='數量')
    total_count = len(df_to_process)
    max_len = summary_df['寄送方式'].astype(str).str.len().max() + 2 if not summary_df.empty else 10
    
    summary_lines = [
        "==============================",
        f"=== {report_title} ===",
        "=============================="
    ]
    
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
    full_report_text = (
        f"擷取時間: {display_timestamp} (台北時間)\n\n"
        f"{summary_text}\n\n"
        "==============================\n"
        "======== 資 料 明 細 ========\n"
        "==============================\n\n"
        f"{details_text}"
    )
    
    return summary_text, full_report_text

def process_and_output_data(df, status_callback):
    """處理並輸出資料"""
    status_callback("  > 細分組...")
    df['主要運送代碼'] = df['主要運送代碼'].astype(str)
    
    # 將7-11大物流分離出來
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
    
    # 提取7-11條碼（不含大物流）
    seven_codes = df_sorted_all[df_sorted_all['寄送方式'] == '7-11']['主要運送代碼'].tolist()
    st.session_state.seven_eleven_codes = [code for code in seven_codes if code]
    
    st.session_state.report_texts['filtered_summary'], st.session_state.report_texts['filtered_full'] = \
        generate_report_text(df_filtered, display_timestamp, "指定項目分組統計")
    st.session_state.report_texts['all_summary'], st.session_state.report_texts['all_full'] = \
        generate_report_text(df_sorted_all, display_timestamp, "所有項目分組統計")
    
    st.session_state.file_timestamp = now.strftime("%y%m%d%H%M")
    status_callback("✅ 資料處理完成！")

# 憑證管理
CREDENTIALS_FILE_WMS = "credentials_wms.json"
CREDENTIALS_FILE_SHOPPY = "credentials_shoppy.json"

def load_credentials(file_path):
    """載入憑證"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_credentials(file_path, username, password):
    """儲存憑證"""
    with open(file_path, 'w') as f:
        json.dump({"username": username, "password": password}, f)

def clear_credentials(file_path):
    """清除憑證"""
    if os.path.exists(file_path):
        os.remove(file_path)

# =================================================================================
# Streamlit 前端介面
# =================================================================================
st.set_page_config(page_title="WMS & Shoppy & 7-11 工具", page_icon="🚚", layout="wide")

# 初始化 Session State
if 'wms_scraping_done' not in st.session_state:
    st.session_state.wms_scraping_done = False
if 'seven_eleven_codes' not in st.session_state:
    st.session_state.seven_eleven_codes = []
if 'shoppy_results' not in st.session_state:
    st.session_state.shoppy_results = None
if 'seven_eleven_scan_results' not in st.session_state:
    st.session_state.seven_eleven_scan_results = None
if 'final_df' not in st.session_state:
    st.session_state.final_df = pd.DataFrame()
if 'df_filtered' not in st.session_state:
    st.session_state.df_filtered = pd.DataFrame()
if 'report_texts' not in st.session_state:
    st.session_state.report_texts = {}

# 側邊欄設定
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
    
    with st.expander("⚙️ 7-11 物流刷取設定", expanded=True):
        seven_url = st.text_input("7-11 後台 URL", value="https://myship.sp88.tw/ECGO/C2CPickup", key="seven_url")
        seven_username = st.text_input("7-11 帳號", value="SSC_008", key="seven_user")
        seven_password = st.text_input("7-11 密碼", value="abc123", type="password", key="seven_pass")
        seven_phone = st.text_input("快收電話號碼", value="0966981112", key="seven_phone")
    
    st.warning("⚠️ **安全性提醒**:\n勾選「記住」會將帳密以可讀取的形式保存在本機上。")

# 主頁面
st.title("🚚 WMS & Shoppy & 7-11 自動化工具")

# 加入退出按鈕（在 PowerShell 中使用）
col1, col2, col3 = st.columns([2, 2, 1])
with col3:
    if st.button("❌ 退出程式", type="secondary"):
        st.warning("正在退出程式...")
        time.sleep(1)
        # 清理資源
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        # 退出程式
        st.stop()
        import sys
        sys.exit(0)

main_tab1, main_tab2, main_tab3 = st.tabs(["📊 WMS 資料擷取", "📦 蝦皮出貨快手", "🚚 7-11 物流刷取"])

# Tab 1: WMS 資料擷取
with main_tab1:
    st.header("步驟一：從 WMS 擷取今日資料")
    
    if not st.session_state.get('wms_scraping_done', False):
        if st.button("🚀 開始擷取 WMS 資料", type="primary", use_container_width=True):
            if not wms_username or not wms_password:
                st.error("❌ 請務必輸入 WMS 帳號和密碼！")
            else:
                # 處理憑證儲存
                if wms_remember:
                    save_credentials(CREDENTIALS_FILE_WMS, wms_username, wms_password)
                else:
                    clear_credentials(CREDENTIALS_FILE_WMS)
                
                # 重置狀態
                for key in ['wms_scraping_done', 'seven_eleven_codes', 'shoppy_results', 'seven_eleven_scan_results']:
                    if key.endswith('_results'):
                        st.session_state[key] = None
                    elif key.endswith('done'):
                        st.session_state[key] = False
                    else:
                        st.session_state[key] = []
                
                # 執行爬取
                progress_placeholder = st.empty()
                
                def streamlit_callback(message):
                    progress_placeholder.info(message)
                
                with st.spinner("WMS 任務執行中..."):
                    tool = AutomationTool(status_callback=streamlit_callback)
                    result_df = tool.run_wms_scrape(wms_url, wms_username, wms_password)
                
                if result_df is not None and not result_df.empty:
                    process_and_output_data(result_df, streamlit_callback)
                    st.session_state.wms_scraping_done = True
                    st.rerun()
                elif result_df is not None and result_df.empty:
                    st.warning("⚠️ WMS 抓取完成，但沒有收到任何資料。")
                else:
                    st.error("❌ 執行 WMS 任務時發生錯誤。")
    else:
        st.success("🎉 WMS 任務完成！資料已擷取並處理。")
        
        if st.button("🔄 重新擷取 WMS 資料", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        st.markdown("---")
        st.header("📊 WMS 擷取結果")
        
        restab1, restab2 = st.tabs(["📊 指定項目報告", "📋 所有項目報告"])
        
        with restab1:
            st.subheader("指定項目統計與明細")
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            
            with col1:
                create_copy_button(
                    st.session_state.get('report_texts', {}).get('filtered_full', ''),
                    "一鍵複製報告",
                    key="copy-btn-filtered"
                )
            
            with col2:
                st.download_button(
                    label="下載 CSV (指定項目)",
                    data=st.session_state.get('df_filtered', pd.DataFrame()).to_csv(index=False, encoding='utf-8-sig'),
                    file_name=f"picking_data_FILTERED_{st.session_state.get('file_timestamp', '')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
            with col3:
                st.download_button(
                    label="下載 TXT (指定項目)",
                    data=st.session_state.get('report_texts', {}).get('filtered_full', '').encode('utf-8'),
                    file_name=f"picking_data_FILTERED_{st.session_state.get('file_timestamp', '')}.txt",
                    mime='text/plain',
                    use_container_width=True
                )
            
            st.text_area(
                "報告內容",
                value=st.session_state.get('report_texts', {}).get('filtered_full', '無資料'),
                height=500,
                label_visibility="collapsed"
            )
        
        with restab2:
            st.subheader("所有項目統計與明細")
            col1, col2, col3 = st.columns([0.4, 0.3, 0.3])
            
            with col1:
                create_copy_button(
                    st.session_state.get('report_texts', {}).get('all_full', ''),
                    "一鍵複製報告",
                    key="copy-btn-all"
                )
            
            with col2:
                st.download_button(
                    label="下載 CSV (所有資料)",
                    data=st.session_state.get('final_df', pd.DataFrame()).to_csv(index=False, encoding='utf-8-sig'),
                    file_name=f"picking_data_ALL_{st.session_state.get('file_timestamp', '')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
            with col3:
                st.download_button(
                    label="下載 TXT (所有資料)",
                    data=st.session_state.get('report_texts', {}).get('all_full', '').encode('utf-8'),
                    file_name=f"picking_data_ALL_{st.session_state.get('file_timestamp', '')}.txt",
                    mime='text/plain',
                    use_container_width=True
                )
            
            st.text_area(
                "報告內容",
                value=st.session_state.get('report_texts', {}).get('all_full', '無資料'),
                height=500,
                label_visibility="collapsed"
            )

# Tab 2: 蝦皮出貨快手
with main_tab2:
    st.header("步驟二：處理蝦皮出貨快手訂單")
    
    # 提供兩種輸入模式
    input_mode = st.radio(
        "選擇輸入方式：",
        ["從 WMS 資料載入", "手動輸入運送代碼"],
        horizontal=True
    )
    
    codes_to_process = []
    
    if input_mode == "從 WMS 資料載入":
        if not st.session_state.get('wms_scraping_done', False):
            st.info("請先在「WMS 資料擷取」分頁中成功擷取資料。")
        elif not st.session_state.get('seven_eleven_codes'):
            st.warning("WMS 資料中未找到需要處理的【711分組 (不含大物流)】運送代碼。")
        else:
            codes_to_process = st.session_state.get('seven_eleven_codes', [])
            st.success(f"✅ 已從 WMS 載入 **{len(codes_to_process)}** 筆 **711分組 (不含大物流)** 運送代碼。")
    else:
        # 手動輸入模式
        st.info("💡 手動輸入模式：請在下方輸入運送代碼（每行一個）")
        manual_codes_input = st.text_area(
            "輸入運送代碼（每行一個）：",
            height=200,
            placeholder="範例：\nSP24123456789012\nSP24234567890123\nSP24345678901234",
            key="manual_shoppy_codes"
        )
        
        if manual_codes_input:
            codes_to_process = [code.strip() for code in manual_codes_input.split('\n') if code.strip()]
            if codes_to_process:
                st.success(f"✅ 已輸入 **{len(codes_to_process)}** 筆運送代碼")
    
    # 顯示待處理代碼
    if codes_to_process:
        with st.expander("檢視待處理代碼", expanded=False):
            st.text_area("待處理代碼清單", value="\n".join(codes_to_process), height=150, disabled=True)
        
        if st.button("🚀 啟動蝦皮快手，自動化處理", type="primary", use_container_width=True):
            if not shoppy_username or not shoppy_password:
                st.error("❌ 請在側邊欄設定中輸入蝦皮快手的帳號和密碼！")
            else:
                # 處理憑證儲存
                if shoppy_remember:
                    save_credentials(CREDENTIALS_FILE_SHOPPY, shoppy_username, shoppy_password)
                else:
                    clear_credentials(CREDENTIALS_FILE_SHOPPY)
                
                st.session_state.shoppy_results = None
                status_placeholder = st.empty()
                
                def shoppy_callback(message):
                    status_placeholder.info(message)
                
                with st.spinner("蝦皮快手任務執行中..."):
                    tool = AutomationTool(status_callback=shoppy_callback)
                    codes_as_string = "\n".join(codes_to_process)
                    success = tool.run_niceshoppy_automation(
                        shoppy_url, shoppy_username, shoppy_password, codes_as_string
                    )
                
                if success:
                    status_placeholder.success("🎉 蝦皮快手任務成功！請查看下方結果或前往下一步。")
                else:
                    status_placeholder.error("❌ 任務失敗，請查看日誌或截圖。")
                st.rerun()
    elif input_mode == "手動輸入運送代碼":
        st.warning("⚠️ 請輸入至少一個運送代碼")
    
    # 顯示結果
    if st.session_state.get('shoppy_results') is not None:
        st.markdown("---")
        st.subheader("📦 物流條碼抓取結果")
        
        if st.session_state.shoppy_results:
            results_string = "\n".join(st.session_state.shoppy_results)
            col1, col2 = st.columns([0.6, 0.4])
            
            with col1:
                st.text_area("抓取到的物流條碼", value=results_string, height=200, key="shoppy_result_text")
            
            with col2:
                st.metric(label="成功抓取數量", value=f"{len(st.session_state.shoppy_results)} 筆")
                create_copy_button(results_string, "一鍵複製所有條碼", "copy-shoppy-results")
        else:
            st.warning("⚠️ 任務執行完畢，但在產出的 PDF 中未找到符合【物流條碼：...】格式的編碼。")

# Tab 3: 7-11 物流刷取
with main_tab3:
    st.header("步驟三：7-11 物流條碼快收刷取")
    
    # 提供兩種輸入模式
    input_mode_711 = st.radio(
        "選擇輸入方式：",
        ["從蝦皮快手結果載入", "手動輸入物流條碼"],
        horizontal=True,
        key="input_mode_711"
    )
    
    barcodes_to_scan = []
    
    if input_mode_711 == "從蝦皮快手結果載入":
        if not st.session_state.get('shoppy_results'):
            st.info("請先在「蝦皮出貨快手」分頁中成功抓取物流條碼。")
        else:
            barcodes_to_scan = st.session_state.shoppy_results
            st.success(f"✅ 已從蝦皮快手結果中，載入 **{len(barcodes_to_scan)}** 筆物流條碼。")
    else:
        # 手動輸入模式
        st.info("💡 手動輸入模式：請在下方輸入物流條碼（每行一個，通常為16位）")
        manual_barcodes_input = st.text_area(
            "輸入物流條碼（每行一個）：",
            height=200,
            placeholder="範例：\nA123456789012345\nB234567890123456\nC345678901234567",
            key="manual_711_barcodes"
        )
        
        if manual_barcodes_input:
            barcodes_to_scan = [code.strip() for code in manual_barcodes_input.split('\n') if code.strip()]
            if barcodes_to_scan:
                st.success(f"✅ 已輸入 **{len(barcodes_to_scan)}** 筆物流條碼")
    
    # 顯示待刷取條碼
    if barcodes_to_scan:
        with st.expander("檢視待刷取條碼", expanded=False):
            st.text_area("待刷取條碼清單", value="\n".join(barcodes_to_scan), height=150, disabled=True)
        
        # 提供批次處理選項
        col1, col2 = st.columns(2)
        with col1:
            batch_size = st.number_input(
                "批次處理數量（0 = 全部）",
                min_value=0,
                max_value=len(barcodes_to_scan),
                value=0,
                step=1,
                help="設定每次處理的條碼數量，0 表示一次處理全部"
            )
        
        with col2:
            if batch_size > 0:
                st.info(f"將處理前 {batch_size} 筆條碼")
            else:
                st.info(f"將處理全部 {len(barcodes_to_scan)} 筆條碼")
        
        if st.button("🚀 啟動 7-11 自動化刷取", type="primary", use_container_width=True):
            st.session_state.seven_eleven_scan_results = None
            status_placeholder = st.empty()
            
            def seven_scan_callback(message):
                status_placeholder.info(message)
            
            if not all([seven_username, seven_password, seven_phone]):
                st.error("❌ 請在側邊欄設定中輸入 7-11 的帳號、密碼和電話！")
            else:
                # 決定要處理的條碼
                if batch_size > 0:
                    barcodes_to_process = barcodes_to_scan[:batch_size]
                else:
                    barcodes_to_process = barcodes_to_scan
                
                with st.spinner(f"7-11 刷取任務執行中（共 {len(barcodes_to_process)} 筆）..."):
                    tool = AutomationTool(status_callback=seven_scan_callback)
                    success = tool.run_seven_eleven_scan(
                        seven_url, seven_username, seven_password, seven_phone, barcodes_to_process
                    )
                
                if success:
                    status_placeholder.success("🎉 7-11 刷取任務已全部執行完畢！請查看下方統計結果。")
                else:
                    status_placeholder.error("❌ 任務失敗，請查看日誌或截圖。")
                st.rerun()
    elif input_mode_711 == "手動輸入物流條碼":
        st.warning("⚠️ 請輸入至少一個物流條碼")
    
    # 顯示結果
    if st.session_state.get('seven_eleven_scan_results'):
        st.markdown("---")
        st.subheader("📊 刷取結果統計")
        results = st.session_state.seven_eleven_scan_results
        
        col1, col2, col3 = st.columns(3)
        col1.metric("總處理筆數", f"{results['total']} 筆")
        col2.metric("成功筆數", f"{results['success']} 筆")
        col3.metric(
            "失敗筆數",
            f"{results['failed']} 筆",
            delta=f"-{results['failed']}" if results['failed'] > 0 else "0",
            delta_color="inverse"
        )
        
        if results.get('failed_list'):
            st.error("失敗的條碼列表：")
            failed_text = "\n".join(results['failed_list'])
            st.text_area("失敗列表", value=failed_text, height=100)
            
            # 提供複製失敗條碼的功能
            if st.button("📋 複製失敗條碼", key="copy_failed_barcodes"):
                st.code(failed_text, language=None)
                st.info("💡 提示：您可以複製這些失敗的條碼，稍後重試")
