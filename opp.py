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
