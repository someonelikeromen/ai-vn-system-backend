import json
import uuid
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# Constants for default paths
CONFIG_DIR = Path(__file__).parent.parent / "data" / "sys_config"
PROVIDERS_FILE = CONFIG_DIR / "llm_providers.json"
AGENTS_FILE = CONFIG_DIR / "agents.json"

class LLMProvider(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    format: str  # openai, gemini, anthropic, ollama, custom
    base_url: str = ""
    api_key: str = ""
    concurrency_limit: int = 0
    fetched_models: List[str] = Field(default_factory=list)

class AgentConfig(BaseModel):
    role: str
    provider_id: Optional[str] = None
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 1_000_000
    top_p: float = 1.0
    top_k: int = 0  # 0 = 不传（使用模型默认值）

class LLMConfigManager:
    """Manages LLM Providers and Agent routing definitions."""
    _instance = None
    _semaphores: Dict[str, asyncio.Semaphore] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.providers: Dict[str, LLMProvider] = {}
        self.agents: Dict[str, AgentConfig] = {}
        self.load_all()

    def load_all(self):
        # Load Providers
        if PROVIDERS_FILE.exists():
            try:
                data = json.loads(PROVIDERS_FILE.read_text("utf-8"))
                for item in data:
                    prov = LLMProvider.model_validate(item)
                    self.providers[prov.id] = prov
            except Exception as e:
                print(f"[LLMConfigManager] Failed to load providers: {e}")

        # Load Agents
        if AGENTS_FILE.exists():
            try:
                data = json.loads(AGENTS_FILE.read_text("utf-8"))
                for role, item in data.items():
                    act = AgentConfig.model_validate(item)
                    self.agents[role] = act
            except Exception as e:
                print(f"[LLMConfigManager] Failed to load agents: {e}")

        self._refresh_semaphores()

    def save_all(self):
        PROVIDERS_FILE.write_text(
            json.dumps([p.model_dump() for p in self.providers.values()], ensure_ascii=False, indent=2),
            "utf-8"
        )
        AGENTS_FILE.write_text(
            json.dumps({role: a.model_dump() for role, a in self.agents.items()}, ensure_ascii=False, indent=2),
            "utf-8"
        )
        self._refresh_semaphores()

    def _refresh_semaphores(self):
        for pid, prov in self.providers.items():
            if prov.concurrency_limit > 0:
                # Only update if missing or limit changed (to not break queued items heavily)
                if pid not in self._semaphores or self._semaphores[pid]._value != prov.concurrency_limit:
                    self._semaphores[pid] = asyncio.Semaphore(prov.concurrency_limit)
            else:
                if pid in self._semaphores:
                    del self._semaphores[pid]

    def get_semaphore(self, provider_id: str) -> Optional[asyncio.Semaphore]:
        return self._semaphores.get(provider_id)

    # --- Provider CRUD ---
    def list_providers(self) -> List[LLMProvider]:
        return list(self.providers.values())
        
    def get_provider(self, provider_id: str) -> Optional[LLMProvider]:
        return self.providers.get(provider_id)
        
    def add_provider(self, provider: LLMProvider) -> LLMProvider:
        self.providers[provider.id] = provider
        self.save_all()
        return provider
        
    def update_provider(self, provider_id: str, updates: dict) -> Optional[LLMProvider]:
        if provider_id not in self.providers:
            return None
        prov = self.providers[provider_id]
        updated_data = prov.model_dump()
        updated_data.update(updates)
        new_prov = LLMProvider.model_validate(updated_data)
        self.providers[provider_id] = new_prov
        self.save_all()
        return new_prov
        
    def delete_provider(self, provider_id: str):
        if provider_id in self.providers:
            del self.providers[provider_id]
            # Clear associated agents mapping to this provider
            for role, ag in list(self.agents.items()):
                if ag.provider_id == provider_id:
                    self.agents[role].provider_id = None
            self.save_all()

    # --- Agent Configuration ---
    def get_agent_config(self, role: str) -> AgentConfig:
        if role not in self.agents:
            return AgentConfig(role=role)
        return self.agents[role]

    def set_agent_config(
        self,
        role: str,
        provider_id: Optional[str],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1_000_000,
        top_p: float = 1.0,
        top_k: int = 0,
    ):
        self.agents[role] = AgentConfig(
            role=role,
            provider_id=provider_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            top_k=top_k,
        )
        self.save_all()

llm_manager = LLMConfigManager()
