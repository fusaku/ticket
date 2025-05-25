from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
import email.utils
import time
import pytz
import requests
import threading

# === 配置项 ===
chromedriver_path = "./chromedriver-mac-arm64/chromedriver"
login_email = "mail@gmail.com"
login_password = "password"

# 全局定时启动时间（日本时间 "HH:MM"，None 表示立即执行）
global_start_time = "00:00"

# 票号和selected_id单独定义，方便修改
ticket_number_1 = "1234"
selected_id_1 = "12345"

ticket_number_2 = "1234"
selected_id_2 = "12345"

add_clicks_num = 2  # 设置点击“添加”按钮的次数

# === URL 模板 ===
BASE_URL = "https://www.confetti-web.com"
LOGIN_URL = f"{BASE_URL}/auth/signin"
TICKET_URL_TEMPLATE = f"{BASE_URL}/events/{{ticket_number}}/tickets?selected={{selected_id}}"

# === 工具函数 ===
def log(msg):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # 毫秒
    print(f"[{now}] {msg}")

def click_when_ready(driver, xpath, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", element)
        log(f"✅ 点击: {xpath}")
    except Exception as e:
        log(f"❌ 点击失败: {e}")

def input_by_id(driver, field_id, text, timeout=10):
    try:
        field = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, field_id)))
        field.clear()
        field.send_keys(text)
    except Exception as e:
        log(f"❌ 输入失败({field_id}): {e}")

def wait_until_target_from_server_precise(target_time_str):
    try:
        server_time = email.utils.parsedate_to_datetime(requests.get(BASE_URL).headers.get('Date'))
        jst = pytz.timezone('Asia/Tokyo')
        server_time_jst = server_time.astimezone(jst)

        local_time = datetime.now(jst)
        offset = server_time_jst - local_time

        target_dt = jst.localize(datetime.strptime(server_time_jst.strftime("%Y-%m-%d") + " " + target_time_str, "%Y-%m-%d %H:%M"))
        if target_dt < server_time_jst:
            target_dt += timedelta(days=1)

        wait_seconds = (target_dt - server_time_jst).total_seconds()
        local_target = local_time + offset + timedelta(seconds=wait_seconds)

        log(f"⏱️ 等待 {wait_seconds:.2f} 秒至 {target_time_str}")
        if wait_seconds > 0.5:
            time.sleep(wait_seconds - 0.5)
        while datetime.now(jst) < local_target:
            time.sleep(0.001)
    except Exception as e:
        log(f"❌ 等待失败: {e}")

def click_until_add_button_appears(driver, seat_xpath, add_button_xpath, add_clicks=2, timeout=0.005, max_attempts=1000):
    def stop_animation_and_expand():
        try:
            driver.execute_script("""
                const li = document.querySelector('li.ticket-sales-configuration');
                if (li && !li.classList.contains('selected')) {
                    li.classList.add('selected');
                }

                const wrapper = li?.querySelector('.tickets-wrapper');
                if (wrapper) {
                    wrapper.style.display = 'block';
                    wrapper.style.maxHeight = 'none';
                    wrapper.style.overflow = 'visible';
                    wrapper.style.transition = 'none';
                    wrapper.querySelectorAll('*').forEach(el => {
                        el.style.transition = 'none';
                        el.style.opacity = '1';
                        el.style.transform = 'none';
                    });
                }
            """)
            log("🎯 动画样式已禁用")
        except Exception as e:
            log(f"⚠️ 动画禁用失败: {e}")

    for attempt in range(max_attempts):
        log(f"🔁 第 {attempt+1} 次点击“席”按钮")
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, seat_xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", element)
            log("✅ 点击“席”按钮成功")
            time.sleep(0.1)
            stop_animation_and_expand()
        except Exception as e:
            log(f"⚠️ 点击失败: {e}")
            continue

        try:
            WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, add_button_xpath))
            )
            log("🎯 成功检测到 '添加' 按钮")

            for i in range(add_clicks):
                try:
                    click_when_ready(driver, add_button_xpath)
                    log(f"✅ 第 {i+1} 次点击 '添加' 成功")
                except Exception as e:
                    log(f"⚠️ 第 {i+1} 次点击 '添加' 失败: {e}")
                    break
            return True

        except Exception:
            log("⏳ '添加' 按钮未出现，继续尝试...")

        time.sleep(0.005)

    log("❌ 多次尝试后仍未检测到 '添加' 按钮")
    return False

# === 保持浏览器活跃线程函数 ===
def keep_browser_alive(driver):
    while True:
        try:
            # 执行一个简单的操作保持浏览器活跃
            driver.execute_script("window.scrollBy(0, 1);")
            time.sleep(10)  # 每10秒保持一次活跃
        except Exception as e:
            log(f"保持活跃时出错: {e}")
            break

# === 抢票线程函数 ===
def ticketing_process_thread(config, wait_event, window_pos_x):
    ticket_number = config["ticket_number"]
    selected_id = config["selected_id"]
    seat_label = config["seat_label"]

    options = Options()
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-fonts")  # 禁用字体
    options.add_argument("--disable-dev-shm-usage")  # 禁用共享内存
    options.add_argument("--disable-logging")  # 禁用日志记录
    options.add_argument("--disable-blink-features=AutomationControlled")  # 禁用自动化检测
    options.add_argument("--disable-web-security")  # 禁用Web安全
    options.add_argument("--disable-software-rasterizer")  # 禁用软件光栅化
    options.add_argument("--disable-hardware-acceleration")  # 禁用硬件加速
    options.add_argument("window-size=800x1000")  # 设置窗口大小
    options.add_argument("--disable-animations")  # 禁用所有动画
    options.add_argument("--disable-history")  # 禁用历史记录
    options.add_argument("--disable-new-tab-preview")  # 禁用新标签页预览
    options.add_argument("--disable-background-timer-throttling")  # 禁用后台定时器节流
    options.add_argument("--disable-backgrounding-occluded-windows")  # 禁用窗口被遮挡时的优化
    options.add_argument("--disable-notifications")  # 禁用通知
    options.add_argument("--disable-infobars")  # 禁用信息条
    options.add_argument("--disable-application-cache")  # 禁用应用缓存
    options.add_argument("--disable-remote-fonts")  # 禁用远程字体
    options.add_argument("--disable-logging")  # 禁用浏览器日志
    options.add_argument("--disable-clipboard")  # 禁用剪贴板
    options.add_argument("--disable-screenshot")  # 禁用屏幕截图
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.plugins": 2,  # 禁用插件
        "profile.managed_default_content_settings.popups": 0,  # 禁用弹窗
        # "profile.managed_default_content_settings.cookies": 2,  # 禁用 cookies
        "profile.managed_default_content_settings.geolocation": 2  # 禁用地理定位
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)
    driver.set_window_position(window_pos_x, 0)
    driver.set_window_size(800, 1000)

    try:
        # 登录
        driver.get(LOGIN_URL)
        input_by_id(driver, "key", login_email)
        input_by_id(driver, "password", login_password)
        click_when_ready(driver, '//button[contains(text(), "ログイン")]')
        WebDriverWait(driver, 10).until(EC.title_contains("マイページ"))
        log(f"✅ 登录成功 [{selected_id}]")

        # 启动保持活跃的线程
        keep_alive_thread = threading.Thread(target=keep_browser_alive, args=(driver,))
        keep_alive_thread.daemon = True  # 让保持活跃的线程在主线程退出时自动结束
        keep_alive_thread.start()

        # 等待抢票时间信号
        wait_event.wait()

        # 到点后打开抢票页面
        log(f"✅ 开始抢票 [{selected_id}]")
        ticket_url = TICKET_URL_TEMPLATE.format(ticket_number=ticket_number, selected_id=selected_id)
        driver.get(ticket_url)
        log(f"✅ 页面打开成功 [{selected_id}]")

        # 抢票流程
        click_until_add_button_appears(
            driver,
            seat_xpath=f'//p[contains(text(), "{seat_label}")]',
            add_button_xpath='//button[contains(@class, "add")]',
            add_clicks=add_clicks_num
        )

        click_when_ready(driver, '//button[contains(text(), "次へ")]')
        log(f"🎫 [{selected_id}] 已进入付款页面 - 请人工处理")

        input(f"[{selected_id}] 按回车关闭浏览器")
    finally:
        driver.quit()

# === 多线程入口 ===
def multi_ticketing():
    ticket_configs = [
    {"ticket_number": ticket_number_1, "selected_id": selected_id_1, "seat_label": "席"},
    {"ticket_number": ticket_number_2, "selected_id": selected_id_2, "seat_label": "席"},
    ]

    wait_event = threading.Event()
    threads = []

    # 每个窗口X坐标，防止重叠 (你可以根据屏幕分辨率调整)
    window_positions_x = [0, 900]

    # 启动线程，线程先登录，登录成功后阻塞等待抢票信号
    for i, config in enumerate(ticket_configs):
        t = threading.Thread(target=ticketing_process_thread, args=(config, wait_event, window_positions_x[i]))
        threads.append(t)
        t.start()

    # 主线程等待抢票时间
    if global_start_time:
        wait_until_target_from_server_precise(global_start_time)

    # 时间到，释放所有线程开始抢票
    wait_event.set()

    for t in threads:
        t.join()

if __name__ == "__main__":
    multi_ticketing()
