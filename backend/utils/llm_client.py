"""
UnifiedLLMClient — LiteLLM 封装的多 Provider LLM 客户端
UnifiedEmbeddingClient — 可切换本地/API 的向量嵌入客户端
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional, Any

from loguru import logger
import litellm

from config_sys.llm_config_manager import llm_manager

# 可重试的异常类型关键词（用于字符串匹配兜底）
_RETRYABLE_KEYWORDS = (
    "timeout", "timed out", "connection", "rate limit", "429", "500", "502", "503", "overloaded",
    "resource exhausted", "service unavailable", "internal server error",
)
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


async def _with_retry(coro_factory, label: str):
    """执行 coro_factory() 最多 _MAX_RETRIES 次，失败时指数退避重试。"""
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro_factory()
        except Exception as e:
            last_exc = e
            err_str = str(e).lower()
            is_retryable = any(kw in err_str for kw in _RETRYABLE_KEYWORDS)
            if not is_retryable:
                # 非网络类错误（如参数错误）直接抛出
                logger.error(f"[LLMClient] {label} 不可重试错误: {e}")
                raise
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"[LLMClient] {label} 第 {attempt+1} 次失败，{delay:.0f}s 后重试: {e}"
            )
            await asyncio.sleep(delay)
    logger.error(f"[LLMClient] {label} 重试 {_MAX_RETRIES} 次后仍失败")
    raise last_exc


# ════════════════════════════════════════════════════════════════════════════
# UnifiedLLMClient
# ════════════════════════════════════════════════════════════════════════════

class UnifiedLLMClient:
    """
    统一 LLM 调用客户端。通过 role 字段路由到对应模型和参数。
    支持：Gemini / OpenAI / Anthropic / Ollama / 自定义兼容 API
    """

    def __init__(self):
        # 设置 LiteLLM 日志级别（避免过多输出）
        litellm.set_verbose = False

    def _build_kwargs(self, role: str, extra: dict = None) -> tuple[dict, str]:
        """返回 (kwargs, provider_id)"""
        agent_cfg = llm_manager.get_agent_config(role)
        provider_id = agent_cfg.provider_id

        kw: dict = {}

        if not provider_id and llm_manager.providers:
            # Fallback to first provider if none is specified and providers exist
            provider_id = list(llm_manager.providers.keys())[0]

        prov = llm_manager.get_provider(provider_id) if provider_id else None

        if prov:
            if prov.format == "ollama":
                base = prov.base_url
                kw["base_url"] = base
                model = agent_cfg.model or (prov.fetched_models[0] if prov.fetched_models else "llama3")
                if not model.startswith("ollama/"):
                    model = f"ollama/{model}"
                kw["model"] = model
            elif prov.format == "gemini":
                kw["model"] = agent_cfg.model or "gemini/gemini-2.0-flash"
                if prov.api_key:
                    kw["api_key"] = prov.api_key
            else:
                # OpenAI, Anthropic, Custom (OpenAI compatible)
                # Use custom_llm_provider so litellm routes correctly WITHOUT
                # ever parsing the model name string for a provider prefix.
                # This allows model names like "假流式/gemini-3.1-pro-high" to
                # pass through intact.
                kw["model"] = agent_cfg.model
                if prov.format == "custom":
                    kw["custom_llm_provider"] = "openai"
                elif prov.format in ("openai", "anthropic", "huggingface", "bedrock", "vertex_ai"):
                    kw["custom_llm_provider"] = prov.format
                if prov.api_key:
                    kw["api_key"] = prov.api_key
                if prov.base_url:
                    kw["base_url"] = prov.base_url
        else:
            kw["model"] = "gemini/gemini-2.0-flash"

        # ── Per-agent inference params (override method-level defaults) ──────
        # extra wins over everything (contains messages, stream flag, etc.)
        # but non-inference keys in extra don't touch these params.
        _INFERENCE_KEYS = {"temperature", "max_tokens", "top_p", "top_k"}
        # Start with agent config values
        kw["temperature"] = agent_cfg.temperature
        kw["max_tokens"] = agent_cfg.max_tokens
        if agent_cfg.top_p != 1.0:
            kw["top_p"] = agent_cfg.top_p
        if agent_cfg.top_k > 0:
            kw["top_k"] = agent_cfg.top_k
        # Apply extra (messages, stream=True, etc.) — inference keys in extra
        # are treated as explicit call-site overrides and win over agent config.
        if extra:
            kw.update(extra)
        return kw, provider_id

    async def chat(
        self,
        messages: list[dict],
        role: str = "chronicler",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """单次非流式对话（自动重试最多 3 次）"""
        kw, provider_id = self._build_kwargs(role, {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        sem = llm_manager.get_semaphore(provider_id) if provider_id else None

        async def _call():
            if sem:
                async with sem:
                    r = await litellm.acompletion(**kw)
            else:
                r = await litellm.acompletion(**kw)
            return r.choices[0].message.content or ""

        return await _with_retry(_call, f"chat(role={role})")

    async def chat_json(
        self,
        messages: list[dict],
        role: str = "exchange",
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> dict | list:
        """对话并解析 JSON 响应"""
        text = await self.chat(messages, role=role, temperature=temperature, max_tokens=max_tokens)
        # 移除可能的 markdown 代码块
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[LLMClient] JSON 解析失败: {e}\n原始响应: {text[:500]}")
            raise ValueError(f"LLM 返回了非法 JSON: {e}")

    async def chat_structured(
        self,
        messages: list[dict],
        role: str = "sandbox",
        temperature: float = 0.3,
    ) -> dict:
        """结构化输出（尝试 JSON，失败时返回 {raw: text}）"""
        try:
            return await self.chat_json(messages, role=role, temperature=temperature)
        except ValueError:
            text = await self.chat(messages, role=role, temperature=temperature)
            return {"raw": text}

    async def stream(
        self,
        messages: list[dict],
        role: str = "chronicler",
        temperature: float = 0.85,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """
        流式生成，逐 token 返回。
        启动阶段（建连）自动重试最多 3 次；一旦开始 yield token 则不再重试。
        """
        kw, provider_id = self._build_kwargs(role, {
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        sem = llm_manager.get_semaphore(provider_id) if provider_id else None

        # 重试获取 response 对象（网络建连阶段）
        async def _start_stream():
            if sem:
                async with sem:
                    return await litellm.acompletion(**kw)
            return await litellm.acompletion(**kw)

        response = await _with_retry(_start_stream, f"stream(role={role})")

        try:
            async for chunk in response:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception as e:
            logger.error(f"[LLMClient] stream 读取失败 (role={role}): {e}")
            raise


# ════════════════════════════════════════════════════════════════════════════
# UnifiedEmbeddingClient
# ════════════════════════════════════════════════════════════════════════════

class UnifiedEmbeddingClient:
    """
    统一向量嵌入客户端。支持3种模式：
      local  — sentence-transformers 本地模型
      openai — OpenAI Embeddings API
      custom — 自定义 OpenAI 兼容 Embedding API
    """

    def __init__(self):
        from config import get_settings
        self._settings = get_settings()
        self._model = None  # 延迟加载

    def _load_local_model(self):
        """延迟加载本地 sentence-transformers 模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                model_name = self._settings.embedding_local_model
                logger.info(f"[EmbeddingClient] 加载本地模型: {model_name}")
                self._model = SentenceTransformer(model_name)
                logger.info(f"[EmbeddingClient] 本地模型加载完成")
            except ImportError:
                raise ImportError(
                    "sentence-transformers 未安装。"
                    "请运行: pip install sentence-transformers\n"
                    "或在 .env 中设置 EMBEDDING_PROVIDER=openai"
                )

    async def embed(self, text: str) -> list[float]:
        """单条文本嵌入"""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入"""
        provider = self._settings.embedding_provider

        if provider == "local":
            return await asyncio.get_event_loop().run_in_executor(
                None, self._embed_local_sync, texts
            )
        elif provider in ("openai", "custom"):
            return await self._embed_api(texts)
        else:
            raise ValueError(f"不支持的 Embedding Provider: {provider}")

    def _embed_local_sync(self, texts: list[str]) -> list[list[float]]:
        """同步本地嵌入（在线程池中运行）"""
        self._load_local_model()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        """API 嵌入（OpenAI / 兼容 API）"""
        s = self._settings
        
        # Try specific embedding key first
        api_key = s.embedding_api_key
        base_url = s.embedding_api_base_url
        
        # Fallback to the first openai compatible provider
        if not api_key:
            for p in llm_manager.providers.values():
                if p.format in ("openai", "custom"):
                    api_key = p.api_key
                    base_url = base_url or p.base_url
                    break

        model = s.embedding_api_model

        try:
            kw = {
                "model": model,
                "input": texts,
            }
            if api_key:
                kw["api_key"] = api_key
            if base_url:
                kw["base_url"] = base_url

            response = await litellm.aembedding(**kw)
            return [r["embedding"] for r in response.data]
        except Exception as e:
            logger.error(f"[EmbeddingClient] API 嵌入失败: {e}")
            raise

    @property
    def dimension(self) -> int:
        """返回当前配置的向量维度"""
        return self._settings.embedding_dimension


# ── 全局单例（启动时初始化）────────────────────────────────────────────────
_llm_client: Optional[UnifiedLLMClient] = None
_embedding_client: Optional[UnifiedEmbeddingClient] = None


def get_llm_client() -> UnifiedLLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = UnifiedLLMClient()
    return _llm_client


def get_embedding_client() -> UnifiedEmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = UnifiedEmbeddingClient()
    return _embedding_client
