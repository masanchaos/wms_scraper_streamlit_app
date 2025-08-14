# 請用這個全新、更穩定的版本來替換掉您原本的 _initialize_driver 函數
def _initialize_driver(self):

        self._update_status("  > [穩定模式] 初始化 WebDriver...")
        chrome_options = Options()
        
        # --- 重要的雲端設定 ---
        chrome_options.add_argument("--headless") # 無頭模式
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        # 直接指向由 packages.txt 安裝的 chromium-browser
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        # --- ---------------- ---

        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        settings = {
           "recentDestinations": [{"id": "Save as PDF", "origin": "local", "account": ""}],
           "selectedDestinationId": "Save as PDF",
           "version": 2
        }
        prefs = {
            'printing.print_preview_sticky_settings.appState': json.dumps(settings),
            'savefile.default_directory': '/tmp'
        }
        chrome_options.add_experimental_option('prefs', prefs)
        chrome_options.add_argument('--kiosk-printing')

        # 直接指向由 packages.txt 安裝的 chromedriver
        service = Service(executable_path="/usr/bin/chromedriver")
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        self._update_status("  > WebDriver 初始化完成。")
        return driver


