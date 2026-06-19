"""四笔钱资产配置智能体 — 应用入口."""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router
from api.rule_routes import rule_router
from api.config_dict_routes import config_dict_router
from api.sop_product_routes import sop_product_router

app = FastAPI(
    title="四笔钱智能投顾",
    description="卡片化+一键智能配仓 · 配置驱动 · 理财经理工作台",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(rule_router)
app.include_router(config_dict_router)
app.include_router(sop_product_router)


@app.on_event("startup")
def _startup_sop_scheduler() -> None:
    from core.sop_batch_scheduler import start_scheduler

    start_scheduler()


FRONTEND_DIR = Path(__file__).parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
