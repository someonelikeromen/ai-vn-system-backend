import { useState, useEffect, useCallback } from 'react';

const FORMATS = [
  { id: 'openai',    label: 'OpenAI / 兼容' },
  { id: 'ollama',    label: 'Ollama (本地)' },
  { id: 'gemini',    label: 'Gemini' },
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'custom',    label: '自定义' }
];

const AGENT_ROLES = [
  { id: 'dm',             label: 'DM',          desc: '状态推理/验证' },
  { id: 'chronicler',     label: '书记员',      desc: '正文生成' },
  { id: 'calibrator',     label: 'Calibrator',  desc: '奖励结算' },
  { id: 'npc_actors',     label: 'NPC',         desc: 'NPC行为' },
  { id: 'style_director', label: '风格导演',    desc: '写作风格' },
  { id: 'exchange',       label: '兑换评估',    desc: '定价与交换' },
  { id: 'planner',        label: '规划师',      desc: '伏笔与叙事' },
];

export default function SettingsModal({ onClose }) {
  const [activeTab, setActiveTab] = useState('providers');
  const [providers, setProviders] = useState([]);
  const [agents, setAgents] = useState({});
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const pRes = await fetch('/api/config/providers');
      if (pRes.ok) {
        setProviders(await pRes.json());
      } else {
        console.error("Failed to fetch providers", pRes.status);
      }
      const aRes = await fetch('/api/config/agents');
      if (aRes.ok) {
        setAgents(await aRes.json());
      } else {
        console.error("Failed to fetch agents", aRes.status);
      }
    } catch (e) {
      console.error("Network or parsing error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box settings-modal" style={{maxWidth: 700}}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 22 }}>⚙️</span>
            <div>
              <div className="modal-title">LLM 模型与接口配置</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>
                配置无数量限制的 API 提供商，并分配给各个 Agent
              </div>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="settings-tabs">
          <button className={`settings-tab ${activeTab === 'providers' ? 'active' : ''}`} onClick={() => setActiveTab('providers')}>
            🌐 API 提供商
          </button>
          <button className={`settings-tab ${activeTab === 'agents' ? 'active' : ''}`} onClick={() => setActiveTab('agents')}>
            🤖 Agent 分配
          </button>
        </div>

        <div className="settings-body" style={{ minHeight: 400 }}>
          {loading ? (
             <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-dim)' }}>加载中…</div>
          ) : activeTab === 'providers' ? (
             <ProvidersTab providers={providers} onRefresh={fetchData} />
          ) : (
             <AgentsTab providers={providers} agents={agents} onRefresh={fetchData} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Providers Tab ────────────────────────────────────────────────────────
function ProvidersTab({ providers, onRefresh }) {
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({});
  const [testResult, setTestResult] = useState('');

  const handleEdit = (p) => {
    setDraft({ ...p, api_key: '' }); // Don't pre-fill masked password
    setEditingId(p.id);
    setTestResult('');
  };

  const handleCreate = () => {
    setDraft({ name: '新提供商', format: 'openai', base_url: '', api_key: '', concurrency_limit: 0, fetched_models: [] });
    setEditingId('new');
    setTestResult('');
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const url = editingId === 'new' ? '/api/config/providers' : `/api/config/providers/${editingId}`;
      const method = editingId === 'new' ? 'POST' : 'PUT';
      const body = {
        name: draft.name, format: draft.format, base_url: draft.base_url,
        api_key: draft.api_key, concurrency_limit: Number(draft.concurrency_limit) || 0
      };
      
      const res = await fetch(url, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
      });
      if (res.ok) {
        setEditingId(null);
        onRefresh();
      } else {
        alert("保存失败: " + (await res.json()).detail);
      }
    } catch (e) {
      alert("错误: " + e.message);
    }
    setSaving(false);
  };

  const handleDelete = async (id) => {
    if (!confirm("确定删除这个提供商吗？关联的 Agent 将失去模型！")) return;
    await fetch(`/api/config/providers/${id}`, { method: 'DELETE' });
    onRefresh();
  };

  const handleFetchModels = async () => {
    if (editingId === 'new') return alert("请先保存提供商，然后再拉取模型列表！");
    setSaving(true);
    try {
      const res = await fetch(`/api/config/providers/${editingId}/fetch_models`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
         setTestResult(`✅ 成功拉取 ${data.count} 个模型`);
         setDraft(d => ({...d, fetched_models: data.models}));
         onRefresh();
      } else {
         setTestResult(`❌ 拉取失败: ${data.detail}`);
      }
    } catch (e) {
      setTestResult(`❌ 错误: ${e.message}`);
    }
    setSaving(false);
  };

  const handleTest = async () => {
    if (editingId === 'new') return alert("请先保存提供商并拉取模型！");
    setSaving(true);
    try {
      const res = await fetch(`/api/config/llm/test`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({provider_id: editingId})
      });
      const data = await res.json();
      setTestResult(res.ok ? `✅ 测试成功: ${data.response}` : `❌ 测试失败: ${data.detail}`);
    } catch (e) {
      setTestResult(`❌ 测试错误: ${e.message}`);
    }
    setSaving(false);
  };

  if (editingId) {
    return (
      <div className="settings-section">
        <div style={{ marginBottom: 15, fontWeight: 'bold' }}>{editingId === 'new' ? '✨ 添加提供商' : '✏️ 编辑提供商'}</div>
        <div className="field-row">
          <Field label="显示名称"><input className="settings-input" value={draft.name} onChange={e => setDraft({...draft, name: e.target.value})} /></Field>
          <Field label="接口类型">
            <select className="settings-select" value={draft.format} onChange={e => setDraft({...draft, format: e.target.value})}>
              {FORMATS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </Field>
        </div>
        <div className="field-row">
          <Field label="Base URL"><input className="settings-input" placeholder="http://..." value={draft.base_url} onChange={e => setDraft({...draft, base_url: e.target.value})} /></Field>
          <Field label="并发上限 (0=无限制)"><input className="settings-input" type="number" value={draft.concurrency_limit} onChange={e => setDraft({...draft, concurrency_limit: e.target.value})} /></Field>
        </div>
        <Field label="API Key" hint={draft.api_key_masked ? `当前已设：${draft.api_key_masked}` : ''}>
          <input className="settings-input" type="password" placeholder="留空则不修改。无需密码的本地请随便写字符" value={draft.api_key} onChange={e => setDraft({...draft, api_key: e.target.value})} autoComplete="new-password" />
        </Field>

        {editingId !== 'new' && (
          <div style={{ marginTop: 15, padding: 10, background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
            <div style={{display:'flex', gap: 10, marginBottom: 10}}>
                <button className="btn btn-ghost btn-sm" onClick={handleFetchModels} disabled={saving}>⬇ 拉取并缓存可用模型</button>
                <button className="btn btn-ghost btn-sm" onClick={handleTest} disabled={saving}>🔌 发送连通测试</button>
            </div>
            {testResult && <div style={{ fontSize: 12, color: testResult.includes('❌') ? 'var(--accent-rose)' : 'var(--accent-emerald)'}}>{testResult}</div>}
            <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 8 }}>已缓存模型: {draft.fetched_models?.length || 0} ({draft.fetched_models?.slice(0,3).join(", ")}...)</div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>保存</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)} disabled={saving}>取消</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 15 }}>
        <button className="btn btn-primary btn-sm" onClick={handleCreate}>+ 添加提供商</button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {providers.map(p => (
          <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.05)', padding: 15, borderRadius: 8 }}>
            <div>
              <div style={{ fontWeight: 'bold' }}>{p.name} <span style={{fontSize: 12, color: 'var(--text-dim)', fontWeight:'normal'}}>({p.format})</span></div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                并发: {p.concurrency_limit || '无限制'} | 缓存模型: {p.fetched_models?.length || 0}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => handleEdit(p)}>编辑</button>
              <button className="btn btn-ghost btn-sm" style={{color: 'var(--accent-rose)'}} onClick={() => handleDelete(p.id)}>删除</button>
            </div>
          </div>
        ))}
        {providers.length === 0 && <div style={{ textAlign: 'center', color: 'var(--text-dim)', padding: 20 }}>暂无提供商，请添加</div>}
      </div>
    </div>
  );
}

// ── Agents Tab ──────────────────────────────────────────────────────────
function AgentsTab({ providers, agents, onRefresh }) {
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState({});
  const [expanded, setExpanded] = useState({});
  // Local draft for number inputs (commit on blur to avoid spamming API)
  const [draft, setDraft] = useState({});

  const getVal = (roleId, key, def) =>
    draft[roleId]?.[key] !== undefined ? draft[roleId][key] : (agents[roleId]?.[key] ?? def);

  const patchDraft = (roleId, key, val) =>
    setDraft(prev => ({ ...prev, [roleId]: { ...(prev[roleId] || {}), [key]: val } }));

  const buildPayload = (roleId, overrides = {}) => {
    const ag = agents[roleId] || {};
    const d  = draft[roleId] || {};
    return {
      provider_id:  overrides.provider_id  ?? ag.provider_id  ?? null,
      model:        overrides.model        ?? ag.model         ?? '',
      temperature:  overrides.temperature  !== undefined ? overrides.temperature  : (d.temperature  ?? ag.temperature  ?? 0.7),
      max_tokens:   overrides.max_tokens   !== undefined ? overrides.max_tokens   : (d.max_tokens   ?? ag.max_tokens   ?? 1000000),
      top_p:        overrides.top_p        !== undefined ? overrides.top_p        : (d.top_p        ?? ag.top_p        ?? 1.0),
      top_k:        overrides.top_k        !== undefined ? overrides.top_k        : (d.top_k        ?? ag.top_k        ?? 0),
    };
  };

  const saveAgent = async (roleId, overrides = {}) => {
    setSaving(true);
    const body = buildPayload(roleId, overrides);
    await fetch(`/api/config/agents/${roleId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    // Clear draft for this role after save
    setDraft(prev => { const n = { ...prev }; delete n[roleId]; return n; });
    setSaving(false);
    onRefresh();
  };

  const handleAgentTest = async (roleId) => {
    const ag = agents[roleId] || {};
    if (!ag.provider_id || !ag.model) return;
    setTestResult(prev => ({ ...prev, [roleId]: '测试中…' }));
    try {
      const res  = await fetch('/api/config/llm/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: roleId }),
      });
      const data = await res.json();
      setTestResult(prev => ({
        ...prev,
        [roleId]: res.ok ? `✅ ${data.response}` : `❌ ${data.detail}`,
      }));
    } catch (e) {
      setTestResult(prev => ({ ...prev, [roleId]: `❌ 错误: ${e.message}` }));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {AGENT_ROLES.map(role => {
        const ag         = agents[role.id] || {};
        const activeProv = providers.find(p => p.id === ag.provider_id);
        const models     = activeProv?.fetched_models || [];
        const isExpanded = expanded[role.id];

        return (
          <div key={role.id} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 8, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.06)' }}>
            {/* ── Header row ── */}
            <div style={{ padding: '12px 15px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <div style={{ fontWeight: 'bold', fontSize: 13 }}>
                  {role.label}
                  <span style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 'normal', marginLeft: 6 }}>{role.desc}</span>
                </div>
              </div>

              {/* ── Provider + Model row ── */}
              <div className="field-row" style={{ marginBottom: 10 }}>
                <Field label="提供商" style={{ flex: '0 0 180px' }}>
                  <select
                    className="settings-select"
                    value={ag.provider_id || ''}
                    onChange={e => saveAgent(role.id, { provider_id: e.target.value || null })}
                  >
                    <option value="">--未选择--</option>
                    {providers.map(p => <option key={p.id} value={p.id}>{p.name} ({p.format})</option>)}
                  </select>
                </Field>

                <Field label="派发模型" style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 5 }}>
                    {/* Text input — always visible */}
                    <input
                      className="settings-input"
                      style={{ flex: 1 }}
                      value={ag.model || ''}
                      placeholder="可手填模型名…"
                      onChange={e => saveAgent(role.id, { model: e.target.value })}
                    />
                    {/* Cached-models dropdown — always rendered, disabled when empty */}
                    <select
                      className="settings-select mini"
                      disabled={models.length === 0}
                      value={models.includes(ag.model) ? ag.model : ''}
                      onChange={e => saveAgent(role.id, { model: e.target.value })}
                      title={models.length === 0 ? '先在「API 提供商」中拉取模型列表' : '从缓存列表中选择'}
                    >
                      <option value="">{models.length === 0 ? '— 无缓存 —' : '缓存选择…'}</option>
                      {models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                    {/* Test button */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleAgentTest(role.id)}
                      disabled={!ag.provider_id || !ag.model}
                    >🔌 链通测试</button>
                  </div>
                  {testResult[role.id] && (
                    <div style={{ fontSize: 11, marginTop: 4, color: testResult[role.id].includes('❌') ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}>
                      {testResult[role.id]}
                    </div>
                  )}
                </Field>
              </div>
            </div>

            {/* ── Advanced params toggle ── */}
            <button
              style={{
                width: '100%', padding: '6px 15px', background: 'rgba(255,255,255,0.03)',
                border: 'none', borderTop: '1px solid rgba(255,255,255,0.06)',
                color: 'var(--text-dim)', fontSize: 11, textAlign: 'left',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
              }}
              onClick={() => setExpanded(prev => ({ ...prev, [role.id]: !prev[role.id] }))}
            >
              <span style={{ transition: 'transform .2s', display: 'inline-block', transform: isExpanded ? 'rotate(90deg)' : 'none' }}>▶</span>
              高级参数
              <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 10 }}>
                温度 {getVal(role.id, 'temperature', 0.7)} &nbsp;|&nbsp;
                上下文 {Number(getVal(role.id, 'max_tokens', 1000000)).toLocaleString()} tokens
              </span>
            </button>

            {isExpanded && (
              <div style={{ padding: '12px 15px 14px', background: 'rgba(0,0,0,0.15)', display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {/* Temperature */}
                <div style={{ flex: '1 1 140px' }}>
                  <ParamLabel>温度 (0–2)</ParamLabel>
                  <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                    <input
                      type="range" min="0" max="2" step="0.05"
                      style={{ flex: 1 }}
                      value={getVal(role.id, 'temperature', 0.7)}
                      onChange={e => patchDraft(role.id, 'temperature', parseFloat(e.target.value))}
                      onMouseUp={() => saveAgent(role.id)}
                    />
                    <input
                      type="number" min="0" max="2" step="0.05"
                      className="settings-input"
                      style={{ width: 58, textAlign: 'center' }}
                      value={getVal(role.id, 'temperature', 0.7)}
                      onChange={e => patchDraft(role.id, 'temperature', parseFloat(e.target.value))}
                      onBlur={() => saveAgent(role.id)}
                    />
                  </div>
                </div>

                {/* Max tokens */}
                <div style={{ flex: '1 1 180px' }}>
                  <ParamLabel>上下文 / Max Tokens</ParamLabel>
                  <input
                    type="number" min="256" max="2000000" step="1024"
                    className="settings-input" style={{ width: '100%' }}
                    value={getVal(role.id, 'max_tokens', 1000000)}
                    onChange={e => patchDraft(role.id, 'max_tokens', parseInt(e.target.value) || 1000000)}
                    onBlur={() => saveAgent(role.id)}
                  />
                </div>

                {/* Top-P */}
                <div style={{ flex: '1 1 140px' }}>
                  <ParamLabel>Top-P (0–1)</ParamLabel>
                  <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                    <input
                      type="range" min="0" max="1" step="0.01"
                      style={{ flex: 1 }}
                      value={getVal(role.id, 'top_p', 1.0)}
                      onChange={e => patchDraft(role.id, 'top_p', parseFloat(e.target.value))}
                      onMouseUp={() => saveAgent(role.id)}
                    />
                    <input
                      type="number" min="0" max="1" step="0.01"
                      className="settings-input"
                      style={{ width: 58, textAlign: 'center' }}
                      value={getVal(role.id, 'top_p', 1.0)}
                      onChange={e => patchDraft(role.id, 'top_p', parseFloat(e.target.value))}
                      onBlur={() => saveAgent(role.id)}
                    />
                  </div>
                </div>

                {/* Top-K */}
                <div style={{ flex: '1 1 120px' }}>
                  <ParamLabel>Top-K (0=禁用)</ParamLabel>
                  <input
                    type="number" min="0" max="200" step="1"
                    className="settings-input" style={{ width: '100%' }}
                    value={getVal(role.id, 'top_k', 0)}
                    onChange={e => patchDraft(role.id, 'top_k', parseInt(e.target.value) || 0)}
                    onBlur={() => saveAgent(role.id)}
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Component Utils ────────────────────────────────────────────────────────
function ParamLabel({ children }) {
  return (
    <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {children}
    </div>
  );
}

function Field({ label, hint, children, style }) {
  return (
    <div className="settings-field" style={style}>
      <div className="settings-label">
        {label}
        {hint && <span className="settings-hint"> — {hint}</span>}
      </div>
      {children}
    </div>
  );
}
