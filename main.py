import os
import requests
from playwright.sync_api import sync_playwright

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

# 你想截图的交易对
SYMBOL = "BINANCE:BTCUSDT" 
# 60代表1小时，240代表4小时，"D"代表日线
INTERVAL = "240"  

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def get_chart_image():
    # 动态生成挂件 HTML
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

    print("启动隐形浏览器截图中...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # 绝招1：直接把网页内容塞进浏览器，避免本地文件权限问题
        page.set_content(html_content)
        
        # 绝招2：TradingView把图表藏在 iframe 里，所以我们等 iframe 加载出来！
        print("等待图表框架加载...")
        page.wait_for_selector("iframe", timeout=20000)
        
        # 绝招3：框架出来后，它还要通过网络去拉取K线数据并渲染。我们强行给它 8 秒钟的耐心！
        print("正在获取最新K线数据并渲染图表，请等待8秒...")
        page.wait_for_timeout(8000)
        
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
    print("发送飞书结果:", res.text)

if __name__ == "__main__":
    image_bytes = get_chart_image()
    if image_bytes:
        token = get_feishu_token()
        image_key = upload_image_to_feishu(image_bytes, token)
        if image_key:
            send_feishu_msg(image_key)
            print("✅ 高清无水印图表发送成功！")
        else:
            print("❌ 图片上传飞书失败")
