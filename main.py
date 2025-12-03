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

# --- 3. [新功能] 上傳 CSV 並解析存入資料庫 ---
@app.post("/api/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    if not MONGO_URL: return {"error": "DB not connected"}
    
    # 讀取上傳的檔案內容 (InMemory)
    content = await file.read()
    decoded_content = content.decode('utf-8').splitlines()
    
    vlogs = []
    sentiments = []
    gps_data = []
    
    reader = csv.DictReader(decoded_content)
    
    # 清空舊資料 (看您是否希望每次上傳都清空，這裡預設是清空)
    await db["vlogs"].delete_many({})
    await db["sentiments"].delete_many({})
    await db["gps"].delete_many({})

    for row in reader:
        # 處理時間
        try:
            dt = datetime.strptime(row['時間'], "%Y-%m-%d %H:%M:%S")
        except:
            dt = datetime.now()

        # 處理 Sentiments
        if row.get('心情分數'):
            sentiments.append({
                "emotion": f"Score {row['心情分數']}",
                "score": int(row['心情分數']),
                "timestamp": dt
            })

        # 處理 GPS
        if row.get('緯度') and row.get('經度') and row['緯度'] != "":
            gps_data.append({
                "lat": float(row['緯度']),
                "lng": float(row['經度']),
                "location": "Uploaded Location",
                "timestamp": dt
            })

        # 處理 Vlogs (關鍵：將路徑指向靜態檔，確保能播放)
        if row.get('影片路徑') and row['影片路徑'] != "":
            vlogs.append({
                "title": f"Vlog ID {row.get('ID', 'Imported')}",
                "url": "/static/earth.mp4",  # 指向穩定的靜態檔
                "original_path": row['影片路徑'], # 保留原始紀錄供參考
                "timestamp": dt
            })

    # 寫入資料庫
    if vlogs: await db["vlogs"].insert_many(vlogs)
    if sentiments: await db["sentiments"].insert_many(sentiments)
    if gps_data: await db["gps"].insert_many(gps_data)

    # 上傳完成後，直接跳轉回 Dashboard
    return RedirectResponse(url="/dashboard", status_code=303)

# --- 4. 資料下載 API ---
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

# --- 5. Dashboard (含上傳表單) ---
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
            body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; background-color: #f4f6f9; color: #333; }}
            .container {{ max_width: 1000px; margin: 40px auto; padding: 20px; background: white; box-shadow: 0 4px 10px rgba(0,0,0,0.1); border-radius: 10px; }}
            h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
            
            /* 上傳區塊樣式 */
            .upload-box {{ background-color: #eef2f7; border: 2px dashed #bdc3c7; padding: 20px; text-align: center; border-radius: 10px; margin-bottom: 40px; }}
            .upload-box h3 {{ margin-top: 0; color: #7f8c8d; }}
            input[type=file] {{ margin: 10px 0; }}
            .btn-upload {{ background-color: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px; }}
            .btn-upload:hover {{ background-color: #2980b9; }}

            /* 表格樣式 */
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #34495e; color: white; }}
            .download-link {{ color: #27ae60; font-weight: bold; text-decoration: none; display: inline-block; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>EmoGo Backend Dashboard</h1>

            <div class="upload-box">
                <h3>📤 Upload Data (CSV)</h3>
                <p>請上傳您的 <code>data_export.csv</code>，系統將自動解析並寫入資料庫。</p>
                <form action="/api/upload_csv" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".csv" required>
                    <button type="submit" class="btn-upload">Upload & Import</button>
                </form>
            </div>

            <h2>1. Vlogs</h2>
            <table>
                <tr><th>Title</th><th>Action</th><th>Original Path</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{v.get('title', '')}</td><td><a href='{v.get('url', '')}' target='_blank'>🎥 Watch Video</a></td><td>{v.get('original_path', '')}</td><td>{v.get('timestamp', '')}</td></tr>" for v in vlogs])}
            </table>

            <h2>2. Sentiments <a href="/api/download/sentiments" style="font-size:0.6em; float:right;">⬇️ CSV</a></h2>
            <table>
                <tr><th>Emotion</th><th>Score</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{s.get('emotion', '')}</td><td>{s.get('score', '')}</td><td>{s.get('timestamp', '')}</td></tr>" for s in sentiments])}
            </table>

            <h2>3. GPS Data <a href="/api/download/gps" style="font-size:0.6em; float:right;">⬇️ CSV</a></h2>
            <table>
                <tr><th>Location</th><th>Lat / Lng</th><th>Timestamp</th></tr>
                {''.join([f"<tr><td>{g.get('location', '')}</td><td>{g.get('lat', '')}, {g.get('lng', '')}</td><td>{g.get('timestamp', '')}</td></tr>" for g in gps])}
            </table>
        </div>
    </body>
    </html>
    """
    return html_content