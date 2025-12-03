import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI()

# --- 資料庫連線 (關鍵修改) ---
# 程式會去讀取 Render 設定的環境變數，不會在程式碼裡暴露密碼
MONGO_URL = os.getenv("MONGODB_URL")

# (選用) 本地端防呆機制：如果在自己電腦跑沒設定變數，會給個提示
if not MONGO_URL:
    print("【警告】未偵測到 MONGODB_URL 環境變數！")
    print("如果您在本地端執行，請確認有設定環境變數，或使用 .env 檔案。")
    # 這裡不設定 fallback，避免意外連到錯誤資料庫
    
client = AsyncIOMotorClient(MONGO_URL)
db = client["EmoGo_Database"]

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Running!"}

# --- 1. 產生假資料的工具 ---
@app.get("/api/insert_fake_data")
async def insert_fake_data():
    vlogs = [
        {"title": "Day 1 in Taipei", "url": "http://video.com/1.mp4", "timestamp": datetime.now()},
        {"title": "Lunch at NTU", "url": "http://video.com/2.mp4", "timestamp": datetime.now()},
    ]
    sentiments = [
        {"emotion": "Happy", "score": 0.95, "timestamp": datetime.now()},
        {"emotion": "Anxious", "score": 0.3, "timestamp": datetime.now()},
    ]
    gps_data = [
        {"lat": 25.0174, "lng": 121.5397, "location": "NTU Library", "timestamp": datetime.now()},
        {"lat": 25.0330, "lng": 121.5654, "location": "Taipei 101", "timestamp": datetime.now()},
    ]
    
    # 寫入資料庫
    if MONGO_URL: # 確保有連線才寫入
        await db["vlogs"].insert_many(vlogs)
        await db["sentiments"].insert_many(sentiments)
        await db["gps"].insert_many(gps_data)
        return {"message": "成功寫入假資料！請重新整理 Dashboard 查看。"}
    else:
        return {"error": "資料庫未連線"}

# --- 2. HTML Dashboard (直接回傳網頁) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    if not MONGO_URL:
         return "<h1>Error: Database not connected. Please check environment variables.</h1>"

    # 從資料庫撈資料
    vlogs = await db["vlogs"].find().to_list(100)
    sentiments = await db["sentiments"].find().to_list(100)
    gps = await db["gps"].find().to_list(100)

    # 用 Python f-string 產生簡單的 HTML 表格
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EmoGo Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #4CAF50; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .section {{ margin-bottom: 50px; }}
        </style>
    </head>
    <body>
        <h1>EmoGo Backend Dashboard</h1>
        
        <div class="section">
            <h2>1. Vlogs (影音日記)</h2>
            <table>
                <tr><th>ID</th><th>Title</th><th>URL</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{str(v.get('_id'))}</td><td>{v.get('title', '')}</td><td>{v.get('url', '')}</td><td>{v.get('timestamp', '')}</td></tr>" for v in vlogs])}
            </table>
        </div>

        <div class="section">
            <h2>2. Sentiments (情緒數據)</h2>
            <table>
                <tr><th>ID</th><th>Emotion</th><th>Score</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{str(s.get('_id'))}</td><td>{s.get('emotion', '')}</td><td>{s.get('score', '')}</td><td>{s.get('timestamp', '')}</td></tr>" for s in sentiments])}
            </table>
        </div>

        <div class="section">
            <h2>3. GPS Coordinates (定位座標)</h2>
            <table>
                <tr><th>ID</th><th>Location</th><th>Lat/Lng</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{str(g.get('_id'))}</td><td>{g.get('location', '')}</td><td>{g.get('lat', '')}, {g.get('lng', '')}</td><td>{g.get('timestamp', '')}</td></tr>" for g in gps])}
            </table>
        </div>

        <div style="text-align: center; margin-top: 50px;">
            <p>Data Source: MongoDB on Render</p>
            <a href="/api/insert_fake_data"><button style="padding: 10px 20px; cursor: pointer;">產生更多假資料 (Insert Fake Data)</button></a>
        </div>
    </body>
    </html>
    """
    return html_content