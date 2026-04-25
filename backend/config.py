"""
零度叙事系统 — 配置加载模块
支持 .env 文件 + 环境变量，所有配置项均有默认值。
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置（通过 .env 或环境变量注入）"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 服务器 ────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── LLM 配置目前已迁移至 llm_config_manager.py ──────────────────────────

    # ── Embedding ─────────────────────────────────────────────
    embedding_provider: Literal["local", "openai", "custom"] = "local"
    embedding_local_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_api_model: str = "text-embedding-3-small"
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimension: int = 384  # local=384, openai-3-small=1536

    # ── 数据库 ────────────────────────────────────────────────
    db_path: str = "./data/novel_system.db"
    chromadb_path: str = "./data/chromadb"
    vector_backend: Literal["chromadb", "faiss"] = "chromadb"

    # ── 文风目录 ──────────────────────────────────────────────
    writing_styles_path: str = "../../writing-styles"

    # ── 系统行为 ──────────────────────────────────────────────
    purity_max_retries: int = 2
    extract_queue_max: int = 50
    recall_top_k: int = 15

    # ── 计算属性 ──────────────────────────────────────────────
    @property
    def db_path_resolved(self) -> Path:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chromadb_path_resolved(self) -> Path:
        p = Path(self.chromadb_path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def writing_styles_dir(self) -> Path:
        p = Path(self.writing_styles_path)
        if not p.is_absolute():
            # 相对于本文件所在目录
            p = (Path(__file__).parent / p).resolve()
        return p

    # get_model_for_role / get_litellm_kwargs deprecated and logic moved to LLMManager


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局设置单例（线程安全，缓存）"""
    return Settings()
