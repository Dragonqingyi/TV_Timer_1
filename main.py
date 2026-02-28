import os
import requests

# 1. 从 GitHub Secrets 读取配置
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
CHART_API_KEY = os.getenv("CHART_API_KEY")

# 【你可以修改这里】你想截图的交易对和时间周期
SYMBOL = "BINANCE:BTCUSDT" 
INTERVAL = "4h"  # 可选: 1h, 4h, 1d 等

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).json()
    return res.get("tenant_access_token")

def get_chart_image():
    # 使用 Chart-img API 获取 TradingView 高级图表截图
    url = f"https://api.chart-img.com/v1/tradingview/advanced-chart?symbol={SYMBOL}&interval={INTERVAL}&theme=dark&width=1920&height=1080"
    if res.status_code == 200:
        return res.content
    else:
        print("获取图表失败:", res.text)
        return None

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
    print(f"正在获取 {SYMBOL} {INTERVAL} 图表...")
    image_bytes = get_chart_image()
    
    if image_bytes:
        print("图表获取成功，正在上传飞书...")
        token = get_feishu_token()
        image_key = upload_image_to_feishu(image_bytes, token)
        
        if image_key:
            print("上传飞书成功，正在发送到群聊...")
            send_feishu_msg(image_key)
            print("✅ 任务全部执行完成！")
        else:
            print("❌ 获取飞书 image_key 失败")
