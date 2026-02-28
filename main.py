import os
import requests
from playwright.sync_api import sync_playwright

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# 接收从 GitHub Actions 传进来的参数，如果没有传，默认是 BTCUSDT 的 1小时(60)
SYMBOL = os.getenv("TV_SYMBOL", "BINANCE:BTCUSDT.P")
INTERVAL = os.getenv("TV_INTERVAL", "60")  

# 给不同的周期起个中文名，用于飞书标题
INTERVAL_MAP = {
    "60": "1小时",
    "240": "4小时",
    "D": "日线",
    "W": "周线"
}
# 获取当前周期的中文名
TIME_TEXT = INTERVAL_MAP.get(INTERVAL, f"{INTERVAL}周期")

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def get_chart_image():
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>body {{ margin: 0; background-color: #131722; }}</style>
    </head>
    <body>
    <div class="tradingview-widget-container">
      <div id="tv_chart"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": 1920,
        "height": 1080,
        "symbol": "{SYMBOL}",
        "interval": "{INTERVAL}",
        "timezone": "Asia/Shanghai",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "tv_chart"
      }});
      </script>
    </div>
    </body>
    </html>
    """

    print(f"启动浏览器截取 {SYMBOL} {TIME_TEXT} 图表中...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_content(html_content)
        page.wait_for_selector("iframe", timeout=20000)
        page.wait_for_timeout(8000)
        image_bytes = page.screenshot(type="png")
        browser.close()
        return image_bytes

def upload_image_to_feishu(image_bytes, token):
    url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "image_type": (None, "message"),
        "image": ("chart.png", image_bytes, "image/png")
    }
    res = requests.post(url, headers=headers, files=files).json()
    return res.get("data", {}).get("image_key")

def send_feishu_msg(image_key):
    # 【升级点】使用飞书互动卡片，带蓝色大标题
    payload = {
        "msg_type": "interactive",
        "card": {
            "elements":[
                {
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "图表"}
                }
            ],
            "header": {
                "title": {
                    "content": f"📈 {SYMBOL} {TIME_TEXT} 收盘图表已生成",
                    "tag": "plain_text"
                },
                "template": "blue"  # 标题栏颜色
            }
        }
    }
    res = requests.post(FEISHU_WEBHOOK, json=payload)
    print("发送飞书结果:", res.text)

if __name__ == "__main__":
    image_bytes = get_chart_image()
    if image_bytes:
        token = get_feishu_token()
        image_key = upload_image_to_feishu(image_bytes, token)
        if image_key:
            send_feishu_msg(image_key)
            print(f"✅ {TIME_TEXT} 图表发送成功！")
