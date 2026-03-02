import os
import time
import json
import requests
from playwright.sync_api import sync_playwright

# =============================
# 1. 基础环境变量
# =============================
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

TV_SYMBOLS_ENV = os.getenv("TV_SYMBOLS", "BINANCE:BTCUSDT.P")
SYMBOLS =[s.strip() for s in TV_SYMBOLS_ENV.split(",")]
INTERVAL = os.getenv("TV_INTERVAL", "60")

INTERVAL_MAP = {"60": "1小时", "240": "4小时", "D": "日线", "W": "周线"}
TIME_TEXT = INTERVAL_MAP.get(INTERVAL, f"{INTERVAL}周期")
MAX_RETRY = 3

# =============================
# 2. 币安实时数据中心 (获取数据面板)
# =============================
def get_market_data(symbol):
    """从币安抓取实时的 价格、涨跌幅、资金费率"""
    # 兼容性处理：只抓取 BINANCE 的品种，如果以后加了美股外汇则跳过
    if "BINANCE:" not in symbol:
        return None
        
    # 将 BINANCE:BTCUSDT.P 提取为干净的 BTCUSDT 给币安接口用
    clean_symbol = symbol.split(":")[-1].replace(".P", "")
    try:
        # 1. 获取价格和 24h 涨跌幅
        ticker_url = f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={clean_symbol}"
        ticker_res = requests.get(ticker_url).json()
        price = float(ticker_res.get('lastPrice', 0))
        change = float(ticker_res.get('priceChangePercent', 0))
        
        # 2. 获取实时资金费率 (核心多空情绪指标)
        fund_url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean_symbol}"
        fund_res = requests.get(fund_url).json()
        funding_rate = float(fund_res.get('lastFundingRate', 0)) * 100
        
        # 3. 组装精美的数据格式
        return {
            "price": f"{price:,.4f}" if price < 10 else f"{price:,.2f}",
            "change": f"+{change:.2f}%" if change > 0 else f"{change:.2f}%",
            "emoji": "🟢" if change > 0 else "🔴",
            "funding_rate": f"{funding_rate:.4f}%"
        }
    except Exception as e:
        print(f"⚠️ {clean_symbol} 币安数据获取失败: {e}")
        return None

# =============================
# 3. 图表截取 (保留了三均线和独立成交量)
# =============================
def get_chart_image(browser, symbol):
    my_indicators =["Volume@tv-basicstudies", "MASimple@tv-basicstudies", "EMA@tv-basicstudies", "WMA@tv-basicstudies"]
    studies_json = json.dumps(my_indicators)
    overrides = {
        "mainSeriesProperties.showVolume": False,
        "volume@tv-basicstudies.volume.color.0": "rgba(255, 82, 82, 0.7)",
        "volume@tv-basicstudies.volume.color.1": "rgba(0, 230, 118, 0.7)",
        "masimple@tv-basicstudies.length": 7, "masimple@tv-basicstudies.plot.color": "#FFFFFF", "masimple@tv-basicstudies.plot.linewidth": 2,
        "ema@tv-basicstudies.length": 30, "ema@tv-basicstudies.plot.color": "#FFD700", "ema@tv-basicstudies.plot.linewidth": 2,
        "wma@tv-basicstudies.length": 120, "wma@tv-basicstudies.plot.color": "#FF00FF", "wma@tv-basicstudies.plot.linewidth": 2,
    }
    overrides_json = json.dumps(overrides)

    html_content = f"""
    <!DOCTYPE html>
    <html><body style="margin:0; background-color:#131722;"><div id="tv_chart"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script type="text/javascript">
    new TradingView.widget({{"width": 1920, "height": 1080, "symbol": "{symbol}", "interval": "{INTERVAL}", "timezone": "Asia/Shanghai", "theme": "dark", "style": "1", "locale": "en", "enable_publishing": false, "hide_top_toolbar": false, "hide_legend": false, "save_image": false, "container_id": "tv_chart", "studies": {studies_json}, "studies_overrides": {overrides_json} }});
    </script></body></html>
    """
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_content(html_content)
    page.wait_for_selector("iframe", timeout=20000)
    page.wait_for_timeout(8000)
    img_bytes = page.screenshot(type="png")
    page.close()
    return img_bytes

# =============================
# 4. 飞书上传与发送
# =============================
def get_feishu_token():
    res = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def upload_image_to_feishu(image_bytes, token):
    headers = {"Authorization": f"Bearer {token}"}
    files = {"image_type": (None, "message"), "image": ("chart.png", image_bytes, "image/png")}
    res = requests.post("https://open.feishu.cn/open-apis/im/v1/images", headers=headers, files=files).json()
    return res.get("data", {}).get("image_key")

def send_feishu_msg(image_key, symbol, data):
    # 将数据和标题优雅地排版
    md_content = f"📈 {symbol} {TIME_TEXT} 收盘图表\n"
    
    # 如果成功获取到了币安数据，则追加显示数据面板
    if data:
        md_content += f"---\n"
        md_content += f"**实时价格：** ${data['price']} ({data['emoji']} {data['change']})\n"
        md_content += f"**资金费率：** {data['funding_rate']} (多空情绪)"

    payload = {
        "msg_type": "interactive",
        "card": {
            "elements":[
                {"tag": "markdown", "content": md_content},
                {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "图表"}}
            ]
        }
    }
    res = requests.post(FEISHU_WEBHOOK, json=payload)
    print(f"👉 {symbol} 发送结果:", res.text)

# =============================
# 5. 主程序执行逻辑
# =============================
def process_symbol(browser, token, symbol):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            print(f"\n--- 开始处理 {symbol} (尝试 {attempt}/{MAX_RETRY}) ---")
            
            # 1. 截取带有指标的图表
            img = get_chart_image(browser, symbol)
            if img:
                # 2. 抓取币安公开 API 的实时数据
                market_data = get_market_data(symbol)
                
                # 3. 将图片上传到飞书
                image_key = upload_image_to_feishu(img, token)
                
                # 4. 发送最终的图文消息
                if image_key:
                    send_feishu_msg(image_key, symbol, market_data)
                    print(f"✅ {symbol} 完成！")
                    return
        except Exception as e:
            print(f"⚠️ {symbol} 处理异常: {e}")
        time.sleep(3)
    print(f"❌ {symbol} 最终失败。\n")

if __name__ == "__main__":
    token = get_feishu_token()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for sym in SYMBOLS:
            process_symbol(browser, token, sym)
        browser.close()
    print("🎉 所有任务全部执行完毕！")
