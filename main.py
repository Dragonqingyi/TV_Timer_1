import os
import requests
from playwright.sync_api import sync_playwright

# 读取飞书配置 (不需要 chart-img 的 key 了)
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# 你想截图的交易对
SYMBOL = "BINANCE:BTCUSDT" 
# 【注意】官方挂件的时间周期格式不同：60代表1小时，240代表4小时，"D"代表日线
INTERVAL = "240"  

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def get_chart_image():
    # 动态生成一个包含 TradingView 官方高清无水印挂件的本地网页
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin:0; padding:0; background-color:#131722;">
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
    with open("chart.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    print("启动隐形浏览器截图中...")
    # 使用 Playwright 启动浏览器
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 强制设置分辨率为 1920x1080
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # 让浏览器打开我们刚刚生成的本地网页
        file_path = f"file://{os.path.abspath('chart.html')}"
        page.goto(file_path)
        
        # 等待图表加载完毕 (最多等15秒)
        page.wait_for_selector("canvas", timeout=15000)
        # 图表出来后再额外等 4 秒，确保 K线和指标渲染得明明白白
        page.wait_for_timeout(4000)
        
        # 咔嚓！截图！
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
    payload = {"msg_type": "image", "content": {"image_key": image_key}}
    res = requests.post(FEISHU_WEBHOOK, json=payload)
    print("发送结果:", res.text)

if __name__ == "__main__":
    image_bytes = get_chart_image()
    if image_bytes:
        token = get_feishu_token()
        image_key = upload_image_to_feishu(image_bytes, token)
        if image_key:
            send_feishu_msg(image_key)
            print("✅ 高清无水印图表发送成功！")
