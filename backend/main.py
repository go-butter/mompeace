from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import init_db
from backend.routers import auth, foods, premium, users, food_log, intake, recommendation


app = FastAPI(title="맘편하게 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def force_utf8_charset(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset" not in content_type:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


# ── 앱 시작 시 DB 초기화 ──────────────────────────────
init_db()


# ── 기본 확인 ─────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "맘편하게 API 서버 정상 작동"}


app.include_router(auth.router)
app.include_router(foods.router)
app.include_router(premium.router)
app.include_router(users.router)
app.include_router(food_log.router)
app.include_router(intake.router)
app.include_router(recommendation.router)

