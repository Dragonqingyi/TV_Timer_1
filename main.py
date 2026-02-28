import os
import json
import time
import requests
from playwright.sync_api import sync_playwright

# =============================
# 配置参数
# =============================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

TV_SYMBOLS_ENV = os.getenv("TV_SYMBOLS", "BINANCE:BTCUSDT.P,BINANCE:ETHUSDT.P,BINANCE:SOLUSDT.P")
SYMBOLS =[s.strip() for s in TV_SYMBOLS_ENV.split(",")]

INTERVAL = os.getenv("TV_INTERVAL", "60")

INTERVAL_MAP = {
    "60": "1小时",
    "240": "4小时",
    "D": "日线",
    "W": "周线"
}
TIME_TEXT = INTERVAL_MAP.get(INTERVAL, f"{INTERVAL}周期")

MAX_RETRY = 3  # 保留 GPT 优秀的重试机制

# =============================
# 飞书 API 交互
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
            "elements":[{
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
    print(f"👉 {symbol} 飞书发送结果:", res.text)

# =============================
# 浏览器截图核心
# =============================
def get_chart_image(browser, symbol):
    # 👇 这里只保留了 MACD 这一项
    my_indicators = [
        "MACD@tv-basicstudies"
    ]
    
    # 将 Python 列表转成 JavaScript 格式
    studies_json = json.dumps(my_indicators)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; background-color:#131722;">
    <div id="tv_chart"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script type="text/javascript">
    new TradingView.widget({{
        "width": 1920,
        "height": 1080,
        "symbol": "{symbol}",
        "interval": "{INTERVAL}",
        "timezone": "Asia/Shanghai",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "tv_chart",
        "studies": {studies_json}  // 👈 注入 MACD
    }});
    </script>
    </body>
    </html>
    """
    
    # 新建标签页
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_content(html_content)
    
    # 等待框架加载
    page.wait_for_selector("iframe", timeout=20000)
    # 额外等待8秒，确保K线和底部的 MACD 副图都完全渲染出来
    page.wait_for_timeout(8000) 
    
    img_bytes = page.screenshot(type="png")
    page.close() # 截完图马上关闭标签页
    return img_bytes

# =============================
# 带有重试机制的单任务处理
# =============================
def process_symbol(browser, token, symbol):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            print(f"\n--- 开始处理 {symbol} (尝试 {attempt}/{MAX_RETRY}) ---")
            img = get_chart_image(browser, symbol)
            
            if img:
                image_key = upload_image_to_feishu(img, token)
                if image_key:
                    send_feishu_msg(image_key, symbol)
                    print(f"✅ {symbol} 完成！")
                    return # 成功就直接退出重试循环
                else:
                    print("❌ 飞书图片上传失败")
        except Exception as e:
            print(f"⚠️ {symbol} 截图出现异常: {e}")
            
        print(f"等待 3 秒后重试...")
        time.sleep(3)

    print(f"❌ {symbol} 连续 {MAX_RETRY} 次均失败，放弃处理。\n")

# =============================
# 主程序
# =============================
if __name__ == "__main__":
    print(f"开始执行任务，需要截图的币种有: {SYMBOLS}")
    token = get_feishu_token()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 放弃多线程，改用最稳定的顺序执行循环
        for sym in SYMBOLS:
            process_symbol(browser, token, sym)
            
        browser.close()

    print("🎉 所有币种全部处理完毕！")
