from fastapi import FastAPI, File, UploadFile
import uvicorn
import numpy as np
import cv2
import io
from core.image_processor import enhance_image_for_ocr
from core.ocr_engine import run_pipeline

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "AI Server is running"}

@app.post("/predict")
async def predict_cccd(file: UploadFile = File(...)):
    # 1. Đọc file ảnh upload lên
    contents = await file.read()
    nparr = np.fromstring(contents, np.uint8)
    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img_np is None:
        return {"error": "Không thể đọc file ảnh"}

    # 2. Chạy quy trình xử lý AI
    # Truyền hàm làm nét vào pipeline
    results = run_pipeline(img_np, enhance_image_for_ocr)
    
    # 3. Trả về kết quả dạng danh sách text
    return {"data": results}

# Nếu chạy trực tiếp file này (để debug)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)