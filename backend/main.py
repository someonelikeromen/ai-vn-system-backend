"""
零度叙事系统 — FastAPI 主入口
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import get_settings
from db.models import init_db
from db.queries import init_db_instance
from config_sys.registry import AttributeSchemaRegistry, ItemTypeRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动 & 关闭"""
    settings = get_settings()

    # 1. 初始化数据库
    logger.info("📦 初始化数据库...")
    await init_db(settings.db_path)
    db = await init_db_instance(settings.db_path)

    # 2. 注册属性体系
    logger.info("📐 注册属性体系...")
    AttributeSchemaRegistry.startup()

    # 3. 注册物品类型
    logger.info("🎒 注册物品类型...")
    ItemTypeRegistry.startup()

    # 4. 验证文风目录
    styles_dir = settings.writing_styles_dir
    if styles_dir.exists():
        style_count = len(list(styles_dir.glob("*.md")))
        logger.info(f"✍️  文风目录就绪: {styles_dir} ({style_count} 个文件)")
    else:
        logger.warning(f"⚠️  文风目录不存在: {styles_dir}")

    # 5. 启动记忆提取队列
    logger.info("🧠 启动记忆提取队列...")
    from memory.extract_queue import get_extract_queue
    extract_queue = get_extract_queue()
    await extract_queue.start()

    logger.info("🚀 零度叙事系统启动完成！")
    
    from config_sys.llm_config_manager import llm_manager
    logger.info(f"   LLM Providers: {len(llm_manager.providers)} configured")
    logger.info(f"   Embedding:    {settings.embedding_provider} ({settings.embedding_local_model if settings.embedding_provider == 'local' else settings.embedding_api_model})")
    logger.info(f"   Vector DB:    {settings.vector_backend}")
    logger.info(f"   DB Path:      {settings.db_path}")

    yield

    # 关闭时
    logger.info("🛑 停止记忆提取队列...")
    await extract_queue.stop()
    from memory.graph import graph_manager
    graph_manager.save_all()
    await db.close()
    logger.info("💤 系统已关闭")


# ── 应用实例 ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="零度叙事多智能体小说系统",
    description=(
        "Zero-Degree Narrative Multi-Agent Novel System — 后端 API\n\n"
        "基于 FastAPI + LangGraph 实现的多智能体小说创作系统。"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS（开发阶段放开所有来源）────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──────────────────────────────────────────────────────────────

from api.novel import router as novel_router
from api.config_api import router as config_router
from api.memory_api import router as memory_router
from api.game import router as game_router
from api.exchange import router as exchange_router
from api.narrator import router as narrator_router
from api.test_runner import router as test_router

app.include_router(novel_router)
app.include_router(config_router)
app.include_router(memory_router)
app.include_router(game_router)
app.include_router(exchange_router)
app.include_router(narrator_router)
app.include_router(test_router)


# ── 健康检查 ──────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
async def root():
    return {
        "service": "零度叙事系统",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    from db.queries import get_db
    try:
        db = get_db()
        count_row = await db._fetchone("SELECT COUNT(*) as n FROM novels")
        return {
            "status": "ok",
            "db": "connected",
            "novels_count": count_row["n"] if count_row else 0,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── 启动入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
