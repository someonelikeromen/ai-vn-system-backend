/**
 * api.js — 后端 API 请求库
 * 使用 Vite 代理转发 /api 请求到 localhost:8000
 * 生产部署时 BASE 改为完整 URL
 */

const BASE = '';  // Vite proxy: /api → http://localhost:8000/api

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── 小说 ─────────────────────────────────────────────────────────────
export const api = {
  // 小说管理
  listNovels:       ()                   => req('/api/novels'),
  createNovel:      (body)               => req('/api/novels', { method: 'POST', body: JSON.stringify(body) }),
  getNovel:         (id)                 => req(`/api/novels/${id}`),
  updateNovel:      (id, body)           => req(`/api/novels/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteNovel:      (id)                 => req(`/api/novels/${id}`, { method: 'DELETE' }),
  initProtagonist:  (id, body)           => req(`/api/novels/${id}/init`, { method: 'POST', body: JSON.stringify(body) }),

  // 会话 / 历史
  getMessages:      (id, limit = 50)     => req(`/api/sessions/${id}/messages?limit=${limit}`),
  getSessionStatus: (id)                 => req(`/api/sessions/${id}/status`),

  // 主角状态
  getProtagonist:   (id)                 => req(`/api/narrator/${id}/protagonist`),
  
  // 章节
  listChapters:     (id)                 => req(`/api/narrator/${id}/chapters`),
  anchorChapter:    (id, body)           => req(`/api/narrator/${id}/chapters`, { method: 'POST', body: JSON.stringify(body) }),
  rollbackChapter:  (id, chId)          => req(`/api/narrator/${id}/chapters/${chId}/rollback`, { method: 'POST' }),

  // 伏笔
  getHooks:         (id)                 => req(`/api/narrator/${id}/hooks`),

  // 兑换
  getCatalog:       (id, refresh=false)  => req(`/api/exchange/${id}/catalog${refresh ? '?refresh=true' : ''}`),
  searchExchange:   (id, body)           => req(`/api/exchange/${id}/search`, { method: 'POST', body: JSON.stringify(body) }),
  evaluateItem:     (id, body)           => req(`/api/exchange/${id}/evaluate`, { method: 'POST', body: JSON.stringify(body) }),
  purchaseItem:     (id, body)           => req(`/api/exchange/${id}/purchase`, { method: 'POST', body: JSON.stringify(body) }),
  reviveCompanion:  (id, ownedId)        => req(`/api/exchange/${id}/companion/${ownedId}/revive`, { method: 'POST' }),
  previewCombatReward: (id, tier, sub='M', killType='defeat') =>
    req(`/api/exchange/${id}/rewards/combat?enemy_tier=${tier}&enemy_tier_sub=${encodeURIComponent(sub)}&kill_type=${killType}`),

  // 世界档案
  getWorldArchive:    (id, key)          => req(`/api/narrator/${id}/world/${encodeURIComponent(key)}`),
  updateWorldArchive: (id, key, body)    => req(`/api/narrator/${id}/world/${encodeURIComponent(key)}`, { method: 'PUT', body: JSON.stringify(body) }),

  // 记忆调试（memory_api vs narrator版）
  memoryStats:      (id)                 => req(`/api/memory/${id}/stats`),
  memoryNodes:      (id, type='', world='') =>
    req(`/api/memory/${id}/nodes${type||world ? '?'+new URLSearchParams({...(type&&{node_type:type}), ...(world&&{world_key:world})}).toString() : ''}`),
  manualRecall:     (id, body)           => req(`/api/memory/${id}/recall`, { method: 'POST', body: JSON.stringify(body) }),
  queueStats:       ()                   => req('/api/memory/queue/stats'),
  getMemoryNodes:   (id, type='', world='', limit=50) =>
    req(`/api/narrator/${id}/memory/nodes?node_type=${encodeURIComponent(type)}&world_key=${encodeURIComponent(world)}&limit=${limit}`),

  // 成就
  getAchievements:  (id)                 => req(`/api/narrator/${id}/achievements`),
  unlockAchievement:(id, body)           => req(`/api/narrator/${id}/achievements/unlock`, { method: 'POST', body: JSON.stringify(body) }),

  // 配置
  getSchemas:       ()                   => req('/api/config/schemas'),
  getItemTypes:     ()                   => req('/api/config/item-types'),
  getLLMConfig:     ()                   => req('/api/config/llm'),
  updateLLMConfig:  (body)               => req('/api/config/llm', { method: 'PATCH', body: JSON.stringify(body) }),
  health:           ()                   => req('/health'),

  // 主角 AI 生成
  getGenerationQuestions: (novelId, charType = '本土', count = 12) =>
    req(`/api/novels/${novelId}/generate-protagonist/questions?char_type=${encodeURIComponent(charType)}&count=${count}`),
  generateProtagonist: (novelId, body) =>
    req(`/api/novels/${novelId}/generate-protagonist`, { method: 'POST', body: JSON.stringify(body) }),

  // 对话回退
  getRollbackSnapshots: (novelId, limit = 3) =>
    req(`/api/sessions/${novelId}/rollback/snapshots?limit=${limit}`),
  rollbackToSnapshot:   (novelId, snapshotId) =>
    req(`/api/sessions/${novelId}/rollback/${snapshotId}`, { method: 'POST' }),
  resetContent: (novelId) =>
    req(`/api/novels/${novelId}/reset-content`, { method: 'POST' }),

  // 人际关系 / NPC
  getNpcs: (novelId) =>
    req(`/api/narrator/${novelId}/npcs`),
};

/**
 * SSE 游戏回合流 — 返回 controller，可用于中止
 * onEvent(type, payload) 接收每个事件
 */
export function streamMessage(novelId, userInput, chapterId, onEvent) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/api/sessions/${novelId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: userInput, chapter_id: chapterId }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        onEvent('error', { content: err.detail || `HTTP ${res.status}` });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split('\n');
        buf = lines.pop(); // 保留不完整行

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              onEvent(payload.type, payload);
            } catch { /* skip malformed */ }
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        onEvent('error', { content: e.message });
      }
    }
  })();

  return controller;
}
