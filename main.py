import os
import requests
from playwright.sync_api import sync_playwright

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# 【核心升级1】接收多个交易对，用逗号分隔。默认填入了三大金刚的永续合约！
TV_SYMBOLS_ENV = os.getenv("TV_SYMBOLS", "BINANCE:BTCUSDT.P,BINANCE:ETHUSDT.P,BINANCE:SOLUSDT.P")
SYMBOLS = [s.strip() for s in TV_SYMBOLS_ENV.split(",")]

INTERVAL = os.getenv("TV_INTERVAL", "60")  

INTERVAL_MAP = {
    "60": "1小时",
    "240": "4小时",
    "D": "日线",
    "W": "周线"
}
TIME_TEXT = INTERVAL_MAP.get(INTERVAL, f"{INTERVAL}周期")

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def get_chart_image(browser, symbol):
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
        "symbol": "{symbol}",
        "interval": "{INTERVAL}",
        "timezone": "Asia/Shanghai",
        "theme": "dark",
        "style": "1",
        "locale": "zh_CN",
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
    print(f"正在截取 {symbol} {TIME_TEXT} 图表...")
    # 新建一个标签页
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_content(html_content)
    page.wait_for_selector("iframe", timeout=20000)
    page.wait_for_timeout(8000) # 给 8 秒钟时间渲染 K线
    image_bytes = page.screenshot(type="png")
    page.close() # 截图完关闭标签页
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

def send_feishu_msg(image_key, symbol):
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
                    "content": f"{symbol} {TIME_TEXT}",
                    "tag": "plain_text"
                },
                "template": "blue"
            }
        }
    }
    res = requests.post(FEISHU_WEBHOOK, json=payload)
    print(f"👉 {symbol} 发送结果:", res.text)

if __name__ == "__main__":
    # 先拿一次飞书钥匙（不用每次都拿）
    token = get_feishu_token()
    
    print(f"本次任务需要截图的币种有: {SYMBOLS}")
    # 【核心升级2】只启动一次浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 循环遍历每一个币种
        for sym in SYMBOLS:
            try:
                image_bytes = get_chart_image(browser, sym)
                if image_bytes:
                    image_key = upload_image_to_feishu(image_bytes, token)
                    if image_key:
                        send_feishu_msg(image_key, sym)
                        print(f"✅ {sym} 发送成功！\n")
            except Exception as e:
                print(f"❌ {sym} 处理失败: {e}")
                
        browser.close()
    print("🎉 所有币种全部发送完毕！")
