"""
API — 配置查询 + 热更新路由
GET  /api/config/schemas          属性体系列表
GET  /api/config/item-types       物品类型列表
GET  /api/config/provider         当前 LLM Provider 信息（脱敏）
GET  /api/config/embedding        Embedding 配置信息
GET  /api/config/llm              完整 LLM 配置（含脱敏密钥）
PATCH /api/config/llm             热更新 LLM 配置（写回 .env + 重载 Settings）
GET  /api/config/writing-styles   文风文件列表
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config_sys.registry import AttributeSchemaRegistry, ItemTypeRegistry

router = APIRouter(prefix="/api/config", tags=["config"])

# .env 文件路径（相对于 backend 目录）
_ENV_PATH = Path(__file__).parent.parent / ".env"


# ── 请求体模型 ────────────────────────────────────────────────────────

class ProviderPayload(BaseModel):
    name: str
    format: str
    base_url: str = ""
    api_key: str = ""
    concurrency_limit: int = 0

class AgentPayload(BaseModel):
    provider_id: Optional[str] = None
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1_000_000
    top_p: float = 1.0
    top_k: int = 0


# ── 工具函数 ──────────────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    """脱敏：前4字符 + *** + 后4字符"""
    if not key or len(key) < 8:
        return "***" if key else ""
    return key[:4] + "***" + key[-4:]


def _read_env() -> dict:
    """读取 .env 文件为 dict"""
    result = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(env_dict: dict) -> None:
    """将 dict 写回 .env（保留注释和原有格式）"""
    if not _ENV_PATH.exists():
        return
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k, _, _ = stripped.partition("=")
        k = k.strip()
        if k in env_dict:
            new_lines.append(f"{k}={env_dict[k]}")
            updated.add(k)
        else:
            new_lines.append(line)
    # 追加新增项
    for k, v in env_dict.items():
        if k not in updated:
            new_lines.append(f"{k}={v}")
    _ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _reload_settings():
    """清除 lru_cache，强制下次调用重新读取配置"""
    from config import get_settings
    get_settings.cache_clear()


# ── 路由 ─────────────────────────────────────────────────────────────

@router.get("/schemas")
async def list_schemas():
    return {
        "schemas": AttributeSchemaRegistry.list_all(),
        "count": len(AttributeSchemaRegistry._schemas),
    }


@router.get("/schemas/{schema_id}")
async def get_schema(schema_id: str):
    schema = AttributeSchemaRegistry.get(schema_id)
    for s in AttributeSchemaRegistry.list_all():
        if s["schema_id"] == schema.schema_id:
            return s
    return {}


@router.get("/item-types")
async def list_item_types():
    return {
        "item_types": ItemTypeRegistry.list_all(),
        "count": len(ItemTypeRegistry._plugins),
    }


@router.get("/item-types/{type_id}")
async def get_item_type(type_id: str):
    try:
        plugin = ItemTypeRegistry.get(type_id)
        return plugin.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/provider")
async def get_provider_info():
    from config import get_settings
    s = get_settings()
    return {
        "default_provider": s.default_llm_provider,
        "models": {
            "chronicler": s.get_model_for_role("chronicler"),
            "dm":         s.get_model_for_role("dm"),
            "exchange":   s.get_model_for_role("exchange"),
            "light":      s.get_model_for_role("npc_actors"),
        },
        "has_gemini_key":    bool(s.gemini_api_key),
        "has_openai_key":    bool(s.openai_api_key),
        "has_anthropic_key": bool(s.anthropic_api_key),
        "ollama_url": s.ollama_base_url if s.default_llm_provider == "ollama" else None,
    }


@router.get("/embedding")
async def get_embedding_info():
    from config import get_settings
    s = get_settings()
    return {
        "provider":       s.embedding_provider,
        "dimension":      s.embedding_dimension,
        "model":          s.embedding_local_model if s.embedding_provider == "local" else s.embedding_api_model,
        "vector_backend": s.vector_backend,
    }


@router.get("/writing-styles")
async def list_writing_styles():
    from config import get_settings
    s = get_settings()
    styles_dir = s.writing_styles_dir
    if not styles_dir.exists():
        return {"styles": [], "error": f"目录不存在: {styles_dir}"}
    files = [f.name for f in styles_dir.iterdir() if f.suffix == ".md"]
    return {"styles": sorted(files), "count": len(files), "path": str(styles_dir)}


# ── LLM 配置 (Providers & Agents) ─────────────────────────────────────────

from config_sys.llm_config_manager import llm_manager, LLMProvider, AgentConfig

@router.get("/providers")
async def get_providers():
    providers = llm_manager.list_providers()
    return [
        {
            **p.model_dump(),
            "api_key_masked": _mask_key(p.api_key) if p.api_key else ""
        } 
        for p in providers
    ]

@router.post("/providers")
async def create_provider(payload: ProviderPayload):
    prov = LLMProvider(
        name=payload.name,
        format=payload.format,
        base_url=payload.base_url,
        api_key=payload.api_key,
        concurrency_limit=payload.concurrency_limit
    )
    return llm_manager.add_provider(prov).model_dump()

@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, payload: ProviderPayload):
    updates = payload.model_dump()
    # Masking preserve logic
    if updates["api_key"] == "" or "***" in updates["api_key"]:
        del updates["api_key"]
    
    prov = llm_manager.update_provider(provider_id, updates)
    if not prov:
        raise HTTPException(404, "Provider not found")
    return prov.model_dump()

@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    llm_manager.delete_provider(provider_id)
    return {"success": True}

@router.post("/providers/{provider_id}/fetch_models")
async def fetch_models_for_provider(provider_id: str):
    import httpx
    prov = llm_manager.get_provider(provider_id)
    if not prov:
        raise HTTPException(404, "Provider not found")
    
    base_url = prov.base_url.rstrip("/")
    if not base_url:
        raise HTTPException(400, "base_url 不能为空")

    if prov.format == "ollama":
        models_url = f"{base_url}/api/tags"
    else:
        models_url = f"{base_url}/models"
        
    headers = {"Content-Type": "application/json"}
    if prov.api_key:
        headers["Authorization"] = f"Bearer {prov.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.get(models_url, headers=headers)
        
        if resp.status_code == 404 and prov.format != "ollama":
            alt_url = base_url.rstrip("/v1") + "/v1/models"
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(alt_url, headers=headers)

        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"接口返回 {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        
        if prov.format == "ollama":
            models = [m.get("name") for m in data.get("models", [])]
        else:
            if isinstance(data, dict) and "data" in data:
                models = [m.get("id", m) if isinstance(m, dict) else str(m) for m in data["data"]]
            elif isinstance(data, list):
                models = [m.get("id", m) if isinstance(m, dict) else str(m) for m in data]
            elif isinstance(data, dict) and "models" in data:
                models = [m.get("id", m) if isinstance(m, dict) else str(m) for m in data["models"]]
            else:
                models = []
        
        models = sorted(set(str(m) for m in models if m))
        llm_manager.update_provider(provider_id, {"fetched_models": models})
        return {"models": models, "count": len(models)}

    except Exception as e:
        raise HTTPException(500, f"获取模型列表失败: {str(e)[:300]}")


@router.get("/agents")
async def get_agents():
    # Pre-defined roles
    roles = ["chronicler", "dm", "exchange", "npc_actors", "calibrator", "style_director", "planner"]
    result = {}
    for role in roles:
        result[role] = llm_manager.get_agent_config(role).model_dump()
    return result

@router.put("/agents/{role}")
async def update_agent(role: str, payload: AgentPayload):
    llm_manager.set_agent_config(
        role,
        provider_id=payload.provider_id,
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        top_p=payload.top_p,
        top_k=payload.top_k,
    )
    return {"success": True}

@router.post("/llm/test")
async def test_llm_connection(body: dict):
    # Tests a specific provider/model combo or a role directly
    import asyncio
    import litellm
    from utils.llm_client import get_llm_client
    
    role = body.get("role")
    provider_id = body.get("provider_id")
    model = body.get("model")
    
    if role:
        # Use existing client setup for the role
        client = get_llm_client()
        try:
            result = await asyncio.wait_for(
                client.chat(messages=[{"role": "user", "content": "1"}], role=role, max_tokens=5),
                timeout=10.0,
            )
            return {"success": True, "response": str(result)[:100]}
        except Exception as e:
            raise HTTPException(400, f"测试失败: {str(e)[:200]}")
    else:
        # Ad-hoc test for provider without saving
        prov = llm_manager.get_provider(provider_id)
        if not prov:
            raise HTTPException(404, "Provider not found")
        
        kw = {"model": model or (prov.fetched_models[0] if prov.fetched_models else "gpt-3.5-turbo")}
        if prov.format == "ollama":
            if not kw["model"].startswith("ollama/"):
                kw["model"] = f"ollama/{kw['model']}"
            kw["base_url"] = prov.base_url
        elif prov.format == "gemini":
            kw["api_key"] = prov.api_key
        else:
            # Use custom_llm_provider so litellm routes correctly without
            # parsing the model name string (model names may contain slashes).
            kw["base_url"] = prov.base_url
            kw["api_key"] = prov.api_key
            if prov.format == "custom":
                kw["custom_llm_provider"] = "openai"
            elif prov.format in ("openai", "anthropic", "huggingface", "bedrock", "vertex_ai"):
                kw["custom_llm_provider"] = prov.format

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(
                    messages=[{"role": "user", "content": "1"}],
                    max_tokens=5, 
                    **kw
                ),
                timeout=10.0
            )
            return {"success": True, "response": response.choices[0].message.content}
        except Exception as e:
            raise HTTPException(400, f"测试失败: {str(e)[:200]}")
