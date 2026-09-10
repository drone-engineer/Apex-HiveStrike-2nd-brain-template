from fastapi import FastAPI

app = FastAPI(
    title="Apex HiveStrike API",
    description="PX4/ArduPilot 비행 로그 분석 및 드론 엔지니어링 백엔드",
    version="0.1.0"
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "platform": "Apex HiveStrike",
        "message": "비행 데이터 분석 엔진 준비 완료"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
