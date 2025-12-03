import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles # <--- 新增這個 import
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI()

# --- 新增：掛載靜態檔案資料夾 ---
# 這樣做之後，您的 earth.mp4 就可以透過 /static/earth.mp4 存取
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 資料庫連線 ---
MONGO_URL = os.getenv("MONGODB_URL")
if not MONGO_URL:
    print("【警告】未偵測到 MONGODB_URL！")

client = AsyncIOMotorClient(MONGO_URL)
db = client["EmoGo_Database"]

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Running!"}

# --- 1. 產生假資料 (改成使用您的 earth.mp4) ---
@app.get("/api/insert_fake_data")
async def insert_fake_data():
    if not MONGO_URL: return {"error": "DB not connected"}

    # 這裡的 url 改成相對路徑 "/static/earth.mp4"
    # 當助教點擊時，瀏覽器會自動加上您的網域名稱
    vlogs = [
        {
            "title": "Earth Rotation (Local File)", 
            "url": "/static/earth.mp4", 
            "timestamp": datetime.now()
        },
        {
            "title": "Earth Rotation (Backup)", 
            "url": "/static/earth.mp4", 
            "timestamp": datetime.now()
        },
    ]
    
    # 為了簡化，我們先只產生 Vlogs，其他的也可以照舊
    sentiments = [
        {"emotion": "Peaceful", "score": 0.99, "timestamp": datetime.now()},
    ]
    gps_data = [
        {"lat": 0.0, "lng": 0.0, "location": "Earth Center", "timestamp": datetime.now()},
    ]
    
    # 清空舊資料
    await db["vlogs"].delete_many({})
    await db["sentiments"].delete_many({})
    await db["gps"].delete_many({})

    # 寫入新資料
    await db["vlogs"].insert_many(vlogs)
    await db["sentiments"].insert_many(sentiments)
    await db["gps"].insert_many(gps_data)
    
    return {"message": "成功寫入！使用本地 earth.mp4 作為測試資料。"}

# --- 2. HTML Dashboard (保持不變，連結會自動變好用) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    if not MONGO_URL: return "<h1>Error: DB not connected</h1>"

    vlogs = await db["vlogs"].find().to_list(100)
    sentiments = await db["sentiments"].find().to_list(100)
    gps = await db["gps"].find().to_list(100)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EmoGo Dashboard</title>
        <style>
            body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 40px; background-color: #f9f9f9; }}
            h1 {{ color: #2c3e50; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; background-color: white; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #3498db; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .btn {{ display: inline-block; padding: 10px 20px; background-color: #27ae60; color: white; text-decoration: none; border-radius: 5px; }}
            .btn:hover {{ background-color: #2ecc71; }}
        </style>
    </head>
    <body>
        <h1>EmoGo Data Dashboard</h1>
        
        <h2>1. Vlogs (Video Links)</h2>
        <table>
            <tr><th>Title</th><th>Video Link</th><th>Timestamp</th></tr>
            {''.join([f"<tr><td>{v.get('title', '')}</td><td><a href='{v.get('url', '')}' target='_blank'>🔴 Watch/Download Video</a></td><td>{v.get('timestamp', '')}</td></tr>" for v in vlogs])}
        </table>

        <h2>2. Sentiments</h2>
        <table>
            <tr><th>Emotion</th><th>Score</th><th>Timestamp</th></tr>
            {''.join([f"<tr><td>{s.get('emotion', '')}</td><td>{s.get('score', '')}</td><td>{s.get('timestamp', '')}</td></tr>" for s in sentiments])}
        </table>

        <h2>3. GPS Coordinates</h2>
        <table>
            <tr><th>Location</th><th>Lat / Lng</th><th>Timestamp</th></tr>
            {''.join([f"<tr><td>{g.get('location', '')}</td><td>{g.get('lat', '')}, {g.get('lng', '')}</td><td>{g.get('timestamp', '')}</td></tr>" for g in gps])}
        </table>

        <div style="text-align: center; margin-top: 50px;">
            <a href="/api/insert_fake_data" class="btn">重置並寫入測試資料 (Reset & Insert Fake Data)</a>
        </div>
    </body>
    </html>
    """
    return html_content