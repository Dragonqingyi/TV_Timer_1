import os
import time
import json
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright


# =============================
# 配置
# =============================

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

TV_SYMBOLS_ENV = os.getenv(
    "TV_SYMBOLS",
    "BINANCE:BTCUSDT.P,BINANCE:ETHUSDT.P,BINANCE:SOLUSDT.P"
)
SYMBOLS = [s.strip() for s in TV_SYMBOLS_ENV.split(",")]

INTERVAL = os.getenv("TV_INTERVAL", "60")

INTERVAL_MAP = {
    "60": "1小时",
    "240": "4小时",
    "D": "日线",
    "W": "周线"
}
TIME_TEXT = INTERVAL_MAP.get(INTERVAL, f"{INTERVAL}周期")

STATE_FILE = "last_run_state.json"
MAX_RETRY = 3
PARALLEL_WORKERS = 3


# =============================
# 时间控制（交易级核心）
# =============================

def wait_until_kline_close(delay_after_close=5):
    """
    等到下一根K线开始 + 延迟几秒，确保数据稳定
    """
    now = datetime.utcnow()

    next_hour = (now.replace(minute=0, second=0, microsecond=0)
                 + timedelta(hours=1))

    sleep_seconds = (next_hour - now).total_seconds() + delay_after_close

    print(f"当前UTC: {now}")
    print(f"等待K线收盘后执行: {next_hour} + {delay_after_close}s")
    print(f"sleep {int(sleep_seconds)} 秒")

    time.sleep(sleep_seconds)


# =============================
# 防重复发送（极重要）
# =============================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def already_sent_this_hour():
    state = load_state()
    last = state.get("last_hour")

    current_hour = datetime.utcnow().strftime("%Y-%m-%d-%H")

    if last == current_hour:
        print("本小时已发送，跳过")
        return True

    state["last_hour"] = current_hour
    save_state(state)
    return False


# =============================
# 飞书
# =============================

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    }).json()
    return res.get("tenant_access_token")


def upload_image_to_feishu(image_bytes, token):
    url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "image_type": (None, "message"),
        "image": ("chart.png", image_bytes, "image/png")
    }
    res = requests.post(url, headers=headers, files=files).json()
    return res.get("data", {}).get("image_key")


def send_feishu_msg(image_key, symbol):
    payload = {
        "msg_type": "interactive",
        "card": {
            "elements": [{
                "tag": "img",
                "img_key": image_key,
                "alt": {"tag": "plain_text", "content": "图表"}
            }],
            "header": {
                "title": {
                    "content": f"{symbol} {TIME_TEXT}",
                    "tag": "plain_text"
                },
                "template": "blue"
            }
        }
    }
    res = requests.post(FEISHU_WEBHOOK, json=payload)
    print(f"{symbol} 发送结果:", res.text)


# =============================
# TradingView 截图（更稳定）
# =============================

def get_chart_image(browser, symbol):
    html = f"""
    <html>
    <body style="margin:0;background:#131722">
    <div id="tv_chart"></div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
    new TradingView.widget({{
        width:1920,
        height:1080,
        symbol:"{symbol}",
        interval:"{INTERVAL}",
        timezone:"Asia/Shanghai",
        theme:"dark",
        style:"1",
        locale:"en",
        container_id:"tv_chart"
    }});
    </script>
    </body>
    </html>
    """

    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_content(html)

    page.wait_for_selector("iframe", timeout=30000)
    page.wait_for_timeout(10000)

    img = page.screenshot(type="png")
    page.close()
    return img


# =============================
# 带重试执行
# =============================

def process_symbol(browser, token, symbol):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            print(f"处理 {symbol} (尝试 {attempt})")

            img = get_chart_image(browser, symbol)
            image_key = upload_image_to_feishu(img, token)

            if image_key:
                send_feishu_msg(image_key, symbol)
                print(f"{symbol} 完成\n")
                return

        except Exception as e:
            print(f"{symbol} 失败: {e}")

        time.sleep(5)

    print(f"{symbol} 最终失败\n")


# =============================
# 主程序
# =============================

if __name__ == "__main__":

    wait_until_kline_close()

    if already_sent_this_hour():
        exit()

    token = get_feishu_token()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = [
                executor.submit(process_symbol, browser, token, sym)
                for sym in SYMBOLS
            ]
            for f in as_completed(futures):
                pass

        browser.close()

    print("全部完成")
