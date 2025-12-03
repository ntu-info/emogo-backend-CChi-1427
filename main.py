import os
import csv
import io
import uuid # 新增 UUID 用來產生亂數 ID
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI()

# --- 1. 靜態檔案設定 ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 2. 資料庫連線 ---
MONGO_URL = os.getenv("MONGODB_URL")
if not MONGO_URL:
    print("【警告】未偵測到 MONGODB_URL！")

client = AsyncIOMotorClient(MONGO_URL)
db = client["EmoGo_Database"]

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

# --- 3. CSV 上傳 API (升級通用版) ---
@app.post("/api/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    if not MONGO_URL: return {"error": "DB not connected"}
    
    content = await file.read()
    
    # [升級1] 使用 utf-8-sig 以處理 Excel 匯出的 BOM 檔頭問題
    try:
        decoded_content = content.decode('utf-8-sig').splitlines()
    except:
        # 萬一 UTF-8 失敗，嘗試 Big5 (常見於 Windows Excel)
        decoded_content = content.decode('big5', errors='ignore').splitlines()
    
    reader = csv.DictReader(decoded_content)
    
    # 這裡可以選擇是否要清空，為了確保您看到資料，建議先保留清空邏輯，或者您可以註解掉
    # await db["vlogs"].delete_many({})
    # await db["sentiments"].delete_many({})
    # await db["gps"].delete_many({})

    for row in reader:
        # [升級2] 彈性 ID：先找 'ID'，找不到找 'id'，再沒有就自動產生亂數 ID
        unique_id = row.get('ID') or row.get('id')
        if not unique_id:
            unique_id = str(uuid.uuid4()) # 自動補發身分證，不再跳過！

        # 處理時間 (嘗試多種欄位名稱)
        time_str = row.get('時間') or row.get('timestamp') or row.get('Time') or row.get('Date')
        try:
            if time_str:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.now()
        except:
            dt = datetime.now()

        # [升級3] 中英欄位名稱通吃
        # 處理 Sentiments
        score_val = row.get('心情分數') or row.get('score') or row.get('Score') or row.get('emotion')
        if score_val:
            sentiment_doc = {
                "emotion": f"Score {score_val}",
                "score": int(score_val),
                "timestamp": dt
            }
            await db["sentiments"].update_one(
                {"_id": unique_id}, {"$set": sentiment_doc}, upsert=True
            )

        # 處理 GPS
        lat = row.get('緯度') or row.get('lat') or row.get('Latitude')
        lng = row.get('經度') or row.get('lng') or row.get('Longitude')
        
        if lat and lng:
            gps_doc = {
                "lat": float(lat),
                "lng": float(lng),
                "location": row.get('location') or "Uploaded Location",
                "timestamp": dt
            }
            await db["gps"].update_one(
                {"_id": unique_id}, {"$set": gps_doc}, upsert=True
            )

        # 處理 Vlogs
        # 只要有一點點像是影片的欄位，我們就建立 Vlog 資料
        video_path = row.get('影片路徑') or row.get('video') or row.get('url') or row.get('path')
        # 甚至是如果這筆資料有 ID 但沒影片欄位，我們也可以預設給它一個假影片(選用)
        if video_path: 
            vlog_doc = {
                "title": f"Vlog {unique_id}",
                "url": "/static/earth.mp4",
                "original_path": video_path,
                "timestamp": dt
            }
            await db["vlogs"].update_one(
                {"_id": unique_id}, {"$set": vlog_doc}, upsert=True
            )

    return RedirectResponse(url="/dashboard", status_code=303)

# --- 4. 下載 API (保持不變) ---
@app.get("/api/download/vlogs")
async def download_vlogs():
    data = await db["vlogs"].find().to_list(1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Title', 'Server URL', 'Original Path (Device)', 'Timestamp'])
    for row in data:
        writer.writerow([row.get('title'), row.get('url'), row.get('original_path'), row.get('timestamp')])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode('utf-8')), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=vlogs_data.csv"})

@app.get("/api/download/sentiments")
async def download_sentiments():
    data = await db["sentiments"].find().to_list(1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Emotion', 'Score', 'Timestamp'])
    for row in data:
        writer.writerow([row.get('emotion'), row.get('score'), row.get('timestamp')])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode('utf-8')), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentiments.csv"})

@app.get("/api/download/gps")
async def download_gps():
    data = await db["gps"].find().to_list(1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Location', 'Latitude', 'Longitude', 'Timestamp'])
    for row in data:
        writer.writerow([row.get('location'), row.get('lat'), row.get('lng'), row.get('timestamp')])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode('utf-8')), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=gps_data.csv"})

# --- 5. Dashboard (前端 UI 保持不變) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    vlogs = await db["vlogs"].find().to_list(100)
    sentiments = await db["sentiments"].find().to_list(100)
    gps = await db["gps"].find().to_list(100)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EmoGo Backend</title>
        <style>
            body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; background-color: #f8f9fa; color: #333; }}
            .container {{ max_width: 1000px; margin: 40px auto; padding: 30px; background: white; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-radius: 12px; }}
            h1 {{ color: #2c3e50; text-align: center; margin-bottom: 40px; font-weight: 600; }}
            .upload-box {{ background-color: #eef2f7; border: 2px dashed #cbd0d6; padding: 25px; text-align: center; border-radius: 10px; margin-bottom: 50px; transition: 0.3s; }}
            .upload-box:hover {{ border-color: #3498db; background-color: #f1f6fa; }}
            .btn-upload {{ background-color: #3498db; color: white; border: none; padding: 10px 25px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; margin-left: 10px; }}
            .btn-upload:hover {{ background-color: #2980b9; }}
            .section-header {{ display: flex; align-items: center; gap: 15px; margin-top: 40px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #eee; }}
            .section-header h2 {{ margin: 0; font-size: 1.5rem; color: #34495e; }}
            .btn {{ text-decoration: none; border-radius: 5px; font-weight: bold; transition: 0.2s; display: inline-block; }}
            .btn-sm {{ font-size: 0.9rem; padding: 6px 15px; }}
            .btn-download {{ background-color: #27ae60; color: white; }}
            .btn-download:hover {{ background-color: #219150; transform: translateY(-1px); }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; background: #fff; }}
            th, td {{ padding: 12px 15px; border-bottom: 1px solid #eee; text-align: left; }}
            th {{ background-color: #f8f9fa; color: #666; font-weight: bold; text-transform: uppercase; font-size: 0.85rem; }}
            .video-link {{ color: #e74c3c; font-weight: bold; text-decoration: none; }}
            .video-link:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>EmoGo Backend Dashboard</h1>
            <div class="upload-box">
                <h3 style="margin-top:0; color:#555;">📤 Upload Any CSV</h3>
                <form action="/api/upload_csv" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".csv" required style="font-size: 1rem;">
                    <button type="submit" class="btn-upload">Upload & Import</button>
                </form>
            </div>

            <div class="section-header">
                <h2>1. Vlogs</h2>
                <a href="/api/download/vlogs" class="btn btn-sm btn-download">⬇️ Download CSV</a>
            </div>
            <table>
                <tr><th>Title</th><th>Action</th><th>Original Path</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{v.get('title', '')}</td><td><a href='{v.get('url', '')}' target='_blank' class='video-link'>🎥 Watch Video</a></td><td>{v.get('original_path', '')}</td><td>{v.get('timestamp', '')}</td></tr>" for v in vlogs])}
            </table>

            <div class="section-header">
                <h2>2. Sentiments</h2>
                <a href="/api/download/sentiments" class="btn btn-sm btn-download">⬇️ Download CSV</a>
            </div>
            <table>
                <tr><th>Emotion</th><th>Score</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{s.get('emotion', '')}</td><td>{s.get('score', '')}</td><td>{s.get('timestamp', '')}</td></tr>" for s in sentiments])}
            </table>

            <div class="section-header">
                <h2>3. GPS Data</h2>
                <a href="/api/download/gps" class="btn btn-sm btn-download">⬇️ Download CSV</a>
            </div>
            <table>
                <tr><th>Location</th><th>Lat / Lng</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{g.get('location', '')}</td><td>{g.get('lat', '')}, {g.get('lng', '')}</td><td>{g.get('timestamp', '')}</td></tr>" for g in gps])}
            </table>
        </div>
    </body>
    </html>
    """
    return html_content