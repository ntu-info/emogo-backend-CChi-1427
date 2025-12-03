import os
import csv
import io
import shutil
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

# --- 3. CSV 上傳 API ---
@app.post("/api/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    if not MONGO_URL: return {"error": "DB not connected"}
    
    content = await file.read()
    decoded_content = content.decode('utf-8').splitlines()
    
    vlogs = []
    sentiments = []
    gps_data = []
    
    reader = csv.DictReader(decoded_content)
    
    # 維持清空邏輯，方便作業展示
    await db["vlogs"].delete_many({})
    await db["sentiments"].delete_many({})
    await db["gps"].delete_many({})

    for row in reader:
        try:
            dt = datetime.strptime(row['時間'], "%Y-%m-%d %H:%M:%S")
        except:
            dt = datetime.now()

        if row.get('心情分數'):
            sentiments.append({
                "emotion": f"Score {row['心情分數']}",
                "score": int(row['心情分數']),
                "timestamp": dt
            })

        if row.get('緯度') and row.get('經度') and row['緯度'] != "":
            gps_data.append({
                "lat": float(row['緯度']),
                "lng": float(row['經度']),
                "location": "Uploaded Location",
                "timestamp": dt
            })

        if row.get('影片路徑') and row['影片路徑'] != "":
            vlogs.append({
                "title": f"Vlog ID {row.get('ID', 'Imported')}",
                "url": "/static/earth.mp4",
                "original_path": row['影片路徑'], # 這裡有存，所以下載時抓得到
                "timestamp": dt
            })

    if vlogs: await db["vlogs"].insert_many(vlogs)
    if sentiments: await db["sentiments"].insert_many(sentiments)
    if gps_data: await db["gps"].insert_many(gps_data)

    return RedirectResponse(url="/dashboard", status_code=303)

# --- 4. 下載 API (新增了 Vlogs 下載) ---

@app.get("/api/download/vlogs")
async def download_vlogs():
    # 從資料庫撈取 Vlogs 資料
    data = await db["vlogs"].find().to_list(1000)
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 設定 CSV 表頭，包含您指定的 Original Path
    writer.writerow(['Title', 'Server URL', 'Original Path (Device)', 'Timestamp'])
    
    for row in data:
        writer.writerow([
            row.get('title'), 
            row.get('url'), 
            row.get('original_path'), 
            row.get('timestamp')
        ])
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')), 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=vlogs_data.csv"}
    )

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

# --- 5. Dashboard (前端顯示) ---
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
            
            /* 上傳區塊 */
            .upload-box {{ background-color: #eef2f7; border: 2px dashed #cbd0d6; padding: 25px; text-align: center; border-radius: 10px; margin-bottom: 50px; transition: 0.3s; }}
            .upload-box:hover {{ border-color: #3498db; background-color: #f1f6fa; }}
            .btn-upload {{ background-color: #3498db; color: white; border: none; padding: 10px 25px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; margin-left: 10px; }}
            .btn-upload:hover {{ background-color: #2980b9; }}

            /* 標題與按鈕並排區塊 */
            .section-header {{ display: flex; align-items: center; gap: 15px; margin-top: 40px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #eee; }}
            .section-header h2 {{ margin: 0; font-size: 1.5rem; color: #34495e; }}
            
            /* 按鈕通用樣式 */
            .btn {{ text-decoration: none; border-radius: 5px; font-weight: bold; transition: 0.2s; display: inline-block; }}
            .btn-sm {{ font-size: 0.9rem; padding: 6px 15px; }}
            .btn-download {{ background-color: #27ae60; color: white; }}
            .btn-download:hover {{ background-color: #219150; transform: translateY(-1px); }}
            
            /* 表格樣式 */
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
                <h3 style="margin-top:0; color:#555;">📤 Upload New Data</h3>
                <form action="/api/upload_csv" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".csv" required style="font-size: 1rem;">
                    <button type="submit" class="btn-upload">Upload & Import CSV</button>
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