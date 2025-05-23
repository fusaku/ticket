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

# === 配置项 ===
chromedriver_path = "./chromedriver-mac-arm64/chromedriver"
ticket_number = "1234"
# session_time = "席"
start_time_str = "21:28"  # 日本时间
login_email = "email@gmail.com"
login_password = "password"

# === 统一的 URL 配置 ===
BASE_URL = "https://www.confetti-web.com"
LOGIN_URL = f"{BASE_URL}/auth/signin"
TICKET_URL_TEMPLATE = f"{BASE_URL}/events/{{ticket_number}}/tickets?selected=123456"  # 使用 .format() 传入编号

# xpath_time_button = f'//p[contains(text(), "{session_time}")]'

# === 点击某个元素，直到它可点击 ===
def click_when_ready(driver, xpath, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", element)
        print(f"✅ 点击: {xpath}")
    except Exception as e:
        print(f"❌ 点击失败: {e}")

def click_until_add_button_appears(driver, seat_xpath, add_button_xpath, add_clicks=2, timeout=0.007, max_attempts=1000):
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
            print("🎯 动画样式已禁用")
        except Exception as e:
            print(f"⚠️ 动画禁用失败: {e}")

    for attempt in range(max_attempts):
        print(f"🔁 第 {attempt+1} 次点击“席”按钮")
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, seat_xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].click();", element)
            print("✅ 点击“席”按钮成功")
            time.sleep(0.01)  # 给 JS 时间插入 DOM
            stop_animation_and_expand()
        except Exception as e:
            print(f"⚠️ 点击失败: {e}")
            continue

        try:
            WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, add_button_xpath))
            )
            print("🎯 成功检测到 '添加' 按钮")

            for i in range(add_clicks):
                try:
                    click_when_ready(driver, add_button_xpath)
                    print(f"✅ 第 {i+1} 次点击 '添加' 成功")
                except Exception as e:
                    print(f"⚠️ 第 {i+1} 次点击 '添加' 失败: {e}")
                    break
            return True

        except Exception:
            print("⏳ '添加' 按钮未出现，继续尝试...")

        time.sleep(0.007)

    print("❌ 多次尝试后仍未检测到 '添加' 按钮")
    return False

# === 输入框自动输入文字（通过ID）===
def input_by_id(driver, field_id, text, timeout=10):
    try:
        field = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.ID, field_id)))
        field.clear()
        field.send_keys(text)
    except Exception as e:
        print(f"❌ 输入失败({field_id}): {e}")

# === 等待服务器时间精确到达目标点（用于抢票时间同步）===
def wait_until_target_from_server_precise(target_time_str):
    try:
        # 获取服务器时间并转为日本时区
        server_time = email.utils.parsedate_to_datetime(requests.get(BASE_URL).headers.get('Date'))
        jst = pytz.timezone('Asia/Tokyo')
        server_time_jst = server_time.astimezone(jst)

        # 当前本地时间（同样为JST）
        local_time = datetime.now(jst)
        offset = server_time_jst - local_time

        # 构建目标时间（如当前日期+设定的抢票时间）
        target_dt = jst.localize(datetime.strptime(server_time_jst.strftime("%Y-%m-%d") + " " + target_time_str, "%Y-%m-%d %H:%M"))
        if target_dt < server_time_jst:
            target_dt += timedelta(days=1)

        wait_seconds = (target_dt - server_time_jst).total_seconds()
        local_target = local_time + offset + timedelta(seconds=wait_seconds)

        print(f"⏱️ 等待 {wait_seconds:.2f} 秒至 {target_time_str}")
        if wait_seconds > 0.5:
            time.sleep(wait_seconds - 0.5)
        while datetime.now(jst) < local_target:
            time.sleep(0.001)
    except Exception as e:
        print(f"❌ 等待失败: {e}")

# === 抢票流程 ===
def ticketing_process():
    # 设置浏览器选项：关闭不必要资源，加快加载速度
    options = Options()
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2
    }
    options.add_experimental_option("prefs", prefs)

    # 启动 Chrome 浏览器
    driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)
    driver.set_window_position(x=0, y=0)
    driver.set_window_size(800, 1000)

    # 打开登录页面并进行登录
    driver.get(LOGIN_URL)
    input_by_id(driver, "key", login_email)
    input_by_id(driver, "password", login_password)
    click_when_ready(driver, '//button[contains(text(), "ログイン")]')

    WebDriverWait(driver, 10).until(EC.title_contains("マイページ"))
    print("✅ 登录成功")

    # 等待到指定的抢票开始时间
    wait_until_target_from_server_precise(start_time_str)

    # 构造抢票页面 URL 并进入
    ticket_url = TICKET_URL_TEMPLATE.format(ticket_number=ticket_number)
    driver.get(ticket_url)
    # WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath_time_button)))

    # 执行抢票点击流程
    # click_when_ready(driver, xpath_time_button)
    click_until_add_button_appears(
    driver,
    seat_xpath='//p[contains(text(), "席")]',
    add_button_xpath='//button[contains(@class, "add")]',
    add_clicks=2  # <<< 控制点击次数
)

    # click_when_ready(driver, '//p[contains(text(), "席")]')
    # click_when_ready(driver, '//button[contains(@class, "add")]')
    click_when_ready(driver, '//button[contains(text(), "次へ")]')

    print("🎫 已进入付款页面，等待人工操作...")

    input("按回车关闭浏览器")
    driver.quit()

# === 主程序入口 ===
if __name__ == "__main__":
    ticketing_process()
