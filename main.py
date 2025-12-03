import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI()

# 設定 CORS (允許前端連線)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 資料庫連線設定 ---
# 在 Render 的 Environment Variables 設定 MONGODB_URL
# 或者暫時將您的連線字串貼在這裡 (不建議提交到 GitHub)
MONGO_URL = os.getenv("MONGODB_URL", "您的_MongoDB_連線字串_mongodb+srv://...")
client = AsyncIOMotorClient(MONGO_URL)
db = client["EmoGo_Database"] # 您可以自訂資料庫名稱

@app.get("/")
async def root():
    return {"message": "EmoGo Backend is Running!"}

# --- [重要] 作業要求的資料匯出 API ---
# 助教將會檢查這個連結
@app.get("/api/export_all")
async def export_all_data():
    # 從三個 Collection 撈取資料
    # 注意：這裡假設您的 Collection 名稱分別為 vlogs, sentiments, gps
    # 如果您存入時用了不同名稱，請記得修改這裡
    try:
        vlogs = await db["vlogs"].find().to_list(length=1000)
        sentiments = await db["sentiments"].find().to_list(length=1000)
        gps = await db["gps"].find().to_list(length=1000)

        # 處理 MongoDB ObjectId 無法直接轉 JSON 的問題
        for doc in vlogs + sentiments + gps:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return {
            "vlogs": vlogs,
            "sentiments": sentiments,
            "gps_coordinates": gps
        }
    except Exception as e:
        return {"error": str(e), "message": "請確認 MongoDB 是否已連線"}

# --- (選用) 用來接收前端資料的 API 範例 ---
# 您需要用這些 API 把資料存進 MongoDB，上面的 export 才有東西看
@app.post("/api/upload_gps")
async def upload_gps(data: dict):
    new_gps = await db["gps"].insert_one(data)
    return {"id": str(new_gps.inserted_id)}

@app.post("/api/upload_sentiment")
async def upload_sentiment(data: dict):
    new_sentiment = await db["sentiments"].insert_one(data)
    return {"id": str(new_sentiment.inserted_id)}

# Vlogs 上傳邏輯較複雜，若作業僅需展示資料結構，可先略過實作檔案儲存，
# 或僅存入 metadata 到 'vlogs' collection。