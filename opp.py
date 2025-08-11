import time
import pandas as pd
import pyperclip
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

# --- 設定區 ---
LOGIN_URL = "https://wms.jenjan.com.tw/"
USERNAME = "jeff02"
PASSWORD = "j93559091"

def login(driver):
    """處理登入流程"""
    print("  > 正在前往登入頁面...")
    driver.get(LOGIN_URL)
    account_xpath = "//input[@placeholder='example@jenjan.com.tw']"
    password_xpath = "//input[@type='password']"
    account_input = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, account_xpath)))
    account_input.click()
    account_input.send_keys(USERNAME)
    password_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, password_xpath)))
    password_input.click()
    password_input.send_keys(PASSWORD)
    password_input.send_keys(Keys.ENTER)
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "app")))
    print("✅ [成功] 登入完成！")

def navigate_to_picking_complete(driver):
    """導航至揀包完成頁面"""
    print("  > 點擊「揀貨管理」菜單...")
    picking_management_xpath = "//a[.//div[text()='揀貨管理']]"
    try:
        picking_management_button = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, picking_management_xpath)))
        picking_management_button.click()
    except (TimeoutException, ElementClickInterceptedException):
        picking_management_button = driver.find_element(By.XPATH, picking_management_xpath)
        driver.execute_script("arguments[0].click();", picking_management_button)
    
    print("  > 等待分頁區塊載入...")
    default_tab_xpath = "//div[contains(@class, 'btn') and contains(., '未揀訂單')]"
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, default_tab_xpath)))
    
    print("  > 點擊「揀包完成」分頁按鈕...")
    picking_complete_tab_xpath = "//div[contains(@class, 'btn') and contains(., '揀包完成')]"
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, picking_complete_tab_xpath))).click()
    print("✅ [成功] 導航至目標頁面！")


def scrape_data(driver):
    """抓取所有頁面的資料 (偵錯模式)"""
    print("  > 點擊查詢按鈕以載入資料...")
    query_button_xpath = "//div[contains(@class, 'btn-primary')]"
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, query_button_xpath))).click()
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'list-items')]/div[contains(@class, 'item')]")))
    print("  > 資料已初步載入。")

    all_data = []
    page_count = 1
    while True:
        print(f"  > 正在抓取第 {page_count} 頁的資料...")
        time.sleep(1.5)
        item_rows_xpath = "//div[contains(@class, 'list-items')]/div[contains(@class, 'item')]"
        rows = driver.find_elements(By.XPATH, item_rows_xpath)
        if not rows:
            print("  > 在 'list-items' 中找不到任何 'item'，停止抓取。")
            break
        
        # ... (抓取資料的 for 迴圈保持不變) ...
        for row in rows:
            shipping_method, tracking_code = "", ""
            try:
                shipping_method = row.find_element(By.XPATH, "./div[2]/div[3]").text.strip()
                tracking_code_input = row.find_element(By.XPATH, "./div[2]/div[4]//input")
                tracking_code = tracking_code_input.get_property('value').strip()
                if shipping_method or tracking_code:
                    all_data.append({"寄送方式": shipping_method, "主要運送代碼": tracking_code})
            except Exception:
                continue

        # --- [主要修改處] ---
        try:
            next_button_xpath = "//button[normalize-space()='下一頁']"
            next_button = driver.find_element(By.XPATH, next_button_xpath)
            if next_button.get_attribute('disabled'):
                print("  > ✅ 「下一頁」按鈕已禁用，已到達最後一頁。")
                break
            else:
                first_row_of_current_page = rows[0]
                driver.execute_script("arguments[0].click();", next_button)
                page_count += 1
                WebDriverWait(driver, 10).until(EC.staleness_of(first_row_of_current_page))
        except Exception as e:
            # 新增這一行來印出詳細的錯誤訊息
            print(f"  > ❗️ 翻頁時發生錯誤，詳細資訊: {e}")
            print("  > ✅ 因翻頁錯誤，資料抓取完成。")
            break
            
    return all_data

def main():
    """主執行函數"""
    print("程式開始...")
    chrome_options = Options()
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    driver = None 
    try:
        print("  > 正在初始化 WebDriver...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        
        print("\n[步驟 1] 正在執行登入...")
        login(driver)
        
        print("\n[步驟 2] 正在透過點擊進行導航...")
        navigate_to_picking_complete(driver)
        
        time.sleep(3) 

        print("\n[步驟 4] 正在執行資料抓取...")
        data = scrape_data(driver)
        
        if not data:
            print("\n[結果] 沒有抓取到任何資料。")
        else:
            df = pd.DataFrame(data)
            print(f"\n✅ [成功] 資料抓取完成！總共抓取到 {len(df)} 筆資料。")
            print("\n--- 資料預覽 ---")
            print(df.head())
                    
    except Exception as e:
        print("\n" + "="*50)
        print(f"❌ [致命錯誤] 程式執行時發生錯誤。")
        print(f"錯誤類型: {type(e).__name__}")
        print(f"錯誤訊息: {e}")
        if driver:
            driver.save_screenshot('fatal_error.png')
            print("已儲存當前錯誤畫面為 fatal_error.png，請查看。")
        print("="*50 + "\n")

    finally:
        if driver:
            print("\n[結束] 準備關閉瀏覽器...")
            driver.quit()
            print("瀏覽器已關閉。")

if __name__ == "__main__":
    main()
