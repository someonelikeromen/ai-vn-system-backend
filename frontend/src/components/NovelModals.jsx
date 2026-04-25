import { useState, useEffect } from "react";
import { api } from "../api.js";
import ProtagonistGeneratorModal from "./ProtagonistGeneratorModal.jsx";

// ═══════════════════════════════════════════════════════════════════════════
// NovelPickerModal — 小说选择 / 创建 / 删除 / 归档
// ═══════════════════════════════════════════════════════════════════════════
export function NovelPickerModal({ novels, currentNovelId, onSelect, onClose, onCreated, onListChanged }) {
  const [view, setView] = useState("list");
  const [title, setTitle] = useState("");
  const [worldType, setWorldType] = useState("multi_world");
  const [schemaId, setSchemaId] = useState("standard_10d");
  const [schemas, setSchemas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showGenerator, setShowGenerator] = useState(false);
  const [heroName, setHeroName] = useState("");
  const [worldKey, setWorldKey] = useState("");
  const [pendingNovelId, setPendingNovelId] = useState("");

  useEffect(() => {
    api.getSchemas().then(r => setSchemas(r.schemas || [])).catch(() => {});
  }, []);

  // ── 删除小说 ──────────────────────────────────────────────────────────
  const handleDelete = async (novelId, novelTitle, e) => {
    e.stopPropagation();
    if (!confirm(`确定删除《${novelTitle}》？\n此操作不可恢复，将删除所有章节和角色数据。`)) return;
    try {
      await api.deleteNovel(novelId);
      onListChanged?.();
    } catch (err) { alert('删除失败：' + err.message); }
  };

  // ── 归档 / 取消归档小说 ───────────────────────────────────────────────
  const handleArchive = async (novelId, isArchived, e) => {
    e.stopPropagation();
    try {
      await api.updateNovel(novelId, { archived: !isArchived });
      onListChanged?.();
    } catch (err) { alert('操作失败：' + err.message); }
  };

  // ── 手动创建小说 ──────────────────────────────────────────────────────
  const handleCreateManual = async () => {
    if (!title.trim()) { setError("Title required"); return; }
    if (!heroName.trim()) { setError("Protagonist name required"); return; }
    setLoading(true); setError("");
    try {
      const data = await api.createNovel({ title, ip_type: "original", world_type: worldType, current_world_key: worldKey, attr_schema_id: schemaId });
      const novel_id = data.novel?.novel_id || data.novel_id;
      await api.initProtagonist(novel_id, { name: heroName, world_key: worldKey });
      await onCreated(novel_id);
      onClose();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  // ── AI 生成主角创建小说 ───────────────────────────────────────────────
  const handleCreateWithAI = async () => {
    if (!title.trim()) { setError("Title required"); return; }
    setLoading(true); setError("");
    try {
      const data = await api.createNovel({ title, ip_type: "original", world_type: worldType, current_world_key: worldKey, attr_schema_id: schemaId });
      const novel_id = data.novel?.novel_id || data.novel_id;
      setPendingNovelId(novel_id);
      setShowGenerator(true);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  if (showGenerator && pendingNovelId) {
    return (
      <ProtagonistGeneratorModal
        novelId={pendingNovelId}
        initialWorldKey={worldKey}
        onClose={() => { setShowGenerator(false); onCreated(pendingNovelId); onClose(); }}
        onGenerated={async () => { setShowGenerator(false); await onCreated(pendingNovelId); onClose(); }}
      />
    );
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel modal-box novel-picker">
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:18 }}>
          <h2 style={{ fontFamily:"var(--font-title)", fontSize:18, color:"var(--accent-blue)" }}>
            {view === "list" ? "📚 选择小说" : "✨ 创建小说"}
          </h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {view === "list" ? (
          <>
            <div className="novel-list">
              {novels.length === 0 && (
                <div style={{ color:"var(--text-dim)", fontSize:13, textAlign:"center", padding:"20px 0" }}>
                  暂无小说，请在下方创建一个。
                </div>
              )}
              {novels.map(n => (
                <div key={n.novel_id}
                  className={`novel-list-item ${n.novel_id === currentNovelId ? "active" : ""}`}
                  onClick={() => { onSelect(n.novel_id); onClose(); }}
                  style={{ position:'relative' }}
                >
                  <div style={{ flex:1, minWidth:0 }}>
                    <div className="novel-list-name">{n.title}</div>
                    <div className="novel-list-meta">
                      {n.world_type} · {n.attr_schema_id}
                      {n.current_world_key && (
                        <span style={{ color:'var(--accent-blue)', marginLeft:6 }}>🌐 {n.current_world_key}</span>
                      )}
                      {n.archived ? <span style={{ color:'var(--text-dim)', marginLeft:6 }}>[已归档]</span> : null}
                    </div>
                  </div>
                  {/* 操作按钮区 — 阻止冒泡到父级的 onClick */}
                  <div style={{ display:'flex', alignItems:'center', gap:4, flexShrink:0 }} onClick={e => e.stopPropagation()}>
                    {n.novel_id === currentNovelId && <span className="badge badge-blue">当前</span>}
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ padding:'2px 6px', fontSize:11, color:'var(--text-dim)' }}
                      onClick={e => handleArchive(n.novel_id, n.archived, e)}
                      title={n.archived ? '取消归档' : '归档此小说'}
                    >{n.archived ? '📂' : '🗃️'}</button>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ padding:'2px 6px', fontSize:11, color:'var(--accent-rose)' }}
                      onClick={e => handleDelete(n.novel_id, n.title, e)}
                      title="永久删除此小说"
                    >🗑️</button>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop:14 }}>
              <button className="btn btn-primary" style={{ width:"100%" }} onClick={() => setView("create")}>
                + 创建小说
              </button>
            </div>
          </>
        ) : (
          <div className="chapter-form">
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>小说标题</label>
              <input className="input-field" placeholder="例如：无限恐怖 2.5R9" value={title} onChange={e => setTitle(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>世界模式</label>
              <select className="input-field" value={worldType} onChange={e => setWorldType(e.target.value)}>
                <option value="multi_world">多世界穿越 (Multi-World)</option>
                <option value="single_world">单世界 (Single World)</option>
                <option value="original_story">原创世界 (Original World)</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>初始世界代码</label>
              <input className="input-field" placeholder="例如：resident_evil_1" value={worldKey} onChange={e => setWorldKey(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>属性系统</label>
              <select className="input-field" value={schemaId} onChange={e => setSchemaId(e.target.value)}>
                {schemas.map(s => <option key={s.schema_id} value={s.schema_id}>{s.name}</option>)}
                {schemas.length === 0 && <option value="standard_10d">标准10维体系 (10D Standard)</option>}
              </select>
            </div>

            <div style={{ borderTop:"1px solid var(--border)", paddingTop:12, marginTop:4 }}>
              <div style={{ fontSize:11, color:"var(--text-dim)", marginBottom:10 }}>── 主角设定 ──</div>
              <button
                className="btn btn-primary"
                style={{ width:"100%", marginBottom:8, background:"linear-gradient(135deg,#7c3aed,#4f9cf9)" }}
                onClick={handleCreateWithAI}
                disabled={loading || !title.trim()}
              >
                {loading ? <><span className="spinner" /> 创建中…</> : "✨ AI 生成主角 (推荐)"}
              </button>
              <div style={{ display:"flex", gap:8, alignItems:"flex-end" }}>
                <div style={{ flex:1 }}>
                  <label style={{ fontSize:11, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>或直接输入姓名</label>
                  <input className="input-field" placeholder="例如：吴森" value={heroName} onChange={e => setHeroName(e.target.value)} />
                </div>
                <button className="btn btn-ghost" onClick={handleCreateManual}
                  disabled={loading || !title.trim() || !heroName.trim()}
                  style={{ flexShrink:0 }}
                >
                  快速创建
                </button>
              </div>
            </div>
            {error && <div style={{ color:"var(--accent-rose)", fontSize:12 }}>⚠️ {error}</div>}
            <div style={{ display:"flex", gap:10 }}>
              <button className="btn btn-ghost" style={{ flex:1 }} onClick={() => { setView("list"); setError(""); }}>返回</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ChapterModal — 固化新章节 + 历史章节 + 对话回退
// ═══════════════════════════════════════════════════════════════════════════
export function ChapterModal({ novelId, onClose, onAnchored, onRollback }) {
  const [tab, setTab]               = useState('anchor');   // 'anchor' | 'history' | 'rollback'
  const [title, setTitle]           = useState('');
  const [summary, setSummary]       = useState('');
  const [arcLabel, setArc]          = useState('');
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState('');
  const [chapters, setChapters]     = useState([]);
  const [rollbacking, setRollbacking] = useState('');
  // 对话回退
  const [snapshots, setSnapshots]   = useState([]);
  const [snapLoading, setSnapLoading] = useState(false);
  const [turnRollbacking, setTurnRollbacking] = useState('');
  const [turnRollbackResult, setTurnRollbackResult] = useState(null);

  useEffect(() => {
    if (tab === 'history') loadChapters();
    if (tab === 'rollback') loadSnapshots();
  }, [tab]);

  const loadChapters = async () => {
    try {
      const { chapters: list } = await api.listChapters(novelId);
      setChapters(list || []);
    } catch { /* ignore */ }
  };

  const loadSnapshots = async () => {
    setSnapLoading(true);
    try {
      const { snapshots: list } = await api.getRollbackSnapshots(novelId, 3);
      setSnapshots(list || []);
    } catch { /* ignore */ } finally { setSnapLoading(false); }
  };

  const handleAnchor = async () => {
    if (!title.trim()) { setError('需要章节标题'); return; }
    setLoading(true); setError('');
    try {
      const res = await api.anchorChapter(novelId, {
        chapter_title:   title,
        chapter_summary: summary,
        arc_label:       arcLabel,
      });
      onAnchored?.(res);
      onClose();
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  };

  const handleRollback = async (ch) => {
    if (!confirm(`确定回滚到「${ch.title}」之前？\n这将清除该章节固化之后的所有消息和记忆节点，操作不可撤销。`)) return;
    setRollbacking(ch.id);
    try {
      await api.rollbackChapter(novelId, ch.id);
      alert(`✅ 已回滚到「${ch.title}」之前`);
      await loadChapters();
    } catch (e) {
      alert('回滚失败：' + e.message);
    } finally { setRollbacking(''); }
  };

  const handleTurnRollback = async (snap) => {
    const preview = snap.messages_preview?.[0]?.preview || '(无预览)';
    if (!confirm(`确定回退这一轮对话？\n\n「${preview.slice(0,40)}…」\n\n回退后该轮消息、XP、积分和记忆图谱均将恢复，操作不可撤销。`)) return;
    setTurnRollbacking(snap.snapshot_id);
    setTurnRollbackResult(null);
    try {
      const res = await api.rollbackToSnapshot(novelId, snap.snapshot_id);
      setTurnRollbackResult(res);
      onRollback?.(res);   // 通知父组件刷新消息列表和主角状态
    } catch (e) {
      alert('回退失败：' + e.message);
    } finally { setTurnRollbacking(''); }
  };

  const EMOTION_COLORS = { family:'#f97316', romance:'#ec4899', friendship:'#22c55e', hostile:'#ef4444', affiliated:'#a78bfa', mixed:'#f59e0b' };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel modal-box chapter-modal">
        <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:14 }}>
          <h2 style={{ fontFamily:"var(--font-title)", fontSize:17, color:"var(--accent-gold)" }}>📌 章节管理</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {/* Tab 切换 */}
        <div style={{ display:'flex', borderBottom:'1px solid var(--border)', marginBottom:14 }}>
          {[['anchor','📌 固化新章节'], ['history','📜 历史章节'], ['rollback','⏪ 对话回退']].map(([id, label]) => (
            <button key={id}
              onClick={() => setTab(id)}
              style={{
                flex:1, padding:'8px 4px', border:'none', cursor:'pointer', background:'transparent',
                color: tab === id ? 'var(--accent-gold)' : 'var(--text-secondary)',
                fontSize:12, fontWeight: tab === id ? 600 : 400,
                borderBottom: tab === id ? '2px solid var(--accent-gold)' : '2px solid transparent',
                fontFamily:'var(--font-ui)',
              }}
            >{label}</button>
          ))}
        </div>

        {/* ── 固化新章节 ── */}
        {tab === 'anchor' && (
          <div className="chapter-form">
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>章节标题 *</label>
              <input className="input-field" placeholder="第1章 · 无限空间" value={title} onChange={e => setTitle(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>篇章标签</label>
              <input className="input-field" placeholder="早期成长篇" value={arcLabel} onChange={e => setArc(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize:12, color:"var(--text-secondary)", display:"block", marginBottom:4 }}>章节总结 (可选)</label>
              <textarea className="input-field" style={{ minHeight:80, resize:"vertical" }}
                placeholder="简要概括本章事件…"
                value={summary} onChange={e => setSummary(e.target.value)} />
            </div>
            <div style={{ background:"rgba(79,156,249,0.06)", border:"1px solid var(--border)", borderRadius:"var(--radius-sm)", padding:"10px 12px", fontSize:12, color:"var(--text-secondary)" }}>
              💡 固化章节会触发记忆压缩并创建一个长期的总结节点。
            </div>
            {error && <div style={{ color:"var(--accent-rose)", fontSize:12 }}>⚠️ {error}</div>}
            <div style={{ display:"flex", gap:10 }}>
              <button className="btn btn-ghost" style={{ flex:1 }} onClick={onClose}>取消</button>
              <button className="btn btn-gold" style={{ flex:2 }} onClick={handleAnchor} disabled={loading}>
                {loading ? <><span className="spinner" /> 固化中…</> : "📌 确认固化"}
              </button>
            </div>
          </div>
        )}

        {/* ── 历史章节 + 回滚 ── */}
        {tab === 'history' && (
          <div>
            {chapters.length === 0 ? (
              <div style={{ textAlign:'center', color:'var(--text-dim)', padding:20, fontSize:13 }}>
                暂无已固化章节
              </div>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:8, maxHeight:360, overflowY:'auto' }}>
                {[...chapters].reverse().map(ch => (
                  <div key={ch.id} style={{
                    display:'flex', alignItems:'center', gap:8,
                    background:'rgba(255,255,255,0.03)', borderRadius:6,
                    border:'1px solid var(--border)', padding:'8px 12px',
                  }}>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div style={{ fontWeight:600, fontSize:13 }}>Ch.{ch.chapter_num} {ch.title}</div>
                      <div style={{ fontSize:11, color:'var(--text-dim)', marginTop:2 }}>
                        {ch.arc_label && <span style={{ marginRight:6 }}>🏷 {ch.arc_label}</span>}
                        {ch.world_key && <span style={{ color:'var(--accent-blue)' }}>🌐 {ch.world_key}</span>}
                        <span style={{ marginLeft:6 }}>{ch.created_at?.slice(0,10)}</span>
                      </div>
                      {ch.summary && (
                        <div style={{ fontSize:11, color:'var(--text-secondary)', marginTop:2, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                          {ch.summary}
                        </div>
                      )}
                    </div>
                    <button
                      className="btn btn-ghost btn-sm"
                      style={{ color:'var(--accent-rose)', flexShrink:0, fontSize:11 }}
                      onClick={() => handleRollback(ch)}
                      disabled={!!rollbacking}
                      title="回滚到此章节固化前的状态"
                    >
                      {rollbacking === ch.id
                        ? <span className="spinner" style={{ width:10, height:10 }} />
                        : '⏪ 回滚'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── 对话回退 ── */}
        {tab === 'rollback' && (
          <div>
            <div style={{ fontSize:12, color:'var(--text-dim)', marginBottom:10, padding:'8px 10px', background:'rgba(239,68,68,0.06)', borderRadius:6, border:'1px solid rgba(239,68,68,0.2)' }}>
              ⚠️ 回退将恢复该轮之前的：积分、XP/熟练度、凭证、状态效果，同时删除对应消息和记忆图谱节点。
            </div>

            {turnRollbackResult && (
              <div style={{ fontSize:12, color:'var(--accent-green)', marginBottom:10, padding:'8px 10px', background:'rgba(34,197,94,0.08)', borderRadius:6, border:'1px solid rgba(34,197,94,0.3)' }}>
                ✅ 回退成功！已删除 {turnRollbackResult.deleted_messages} 条消息，
                图谱清除 {turnRollbackResult.graph_removed || 0} 个节点，
                积分已恢复至 {turnRollbackResult.protagonist_points}
              </div>
            )}

            {snapLoading ? (
              <div style={{ textAlign:'center', color:'var(--text-dim)', padding:24 }}>
                <span className="spinner" /> 加载快照…
              </div>
            ) : snapshots.length === 0 ? (
              <div style={{ textAlign:'center', color:'var(--text-dim)', padding:24, fontSize:13 }}>
                暂无可回退的快照（需先进行至少1轮对话）
              </div>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {snapshots.map((snap, idx) => {
                  const userMsg = snap.messages_preview?.find(m => m.role === 'user');
                  const timeStr = snap.created_at?.slice(0,16).replace('T',' ') || '';
                  return (
                    <div key={snap.snapshot_id} style={{
                      display:'flex', alignItems:'flex-start', gap:8,
                      background:'rgba(255,255,255,0.03)', borderRadius:6,
                      border:'1px solid var(--border)', padding:'10px 12px',
                    }}>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
                          <span style={{ fontSize:11, background:'rgba(239,68,68,0.15)', color:'var(--accent-rose)', borderRadius:10, padding:'1px 7px' }}>
                            第 {snapshots.length - idx} 回合前
                          </span>
                          <span style={{ fontSize:11, color:'var(--text-dim)' }}>{timeStr}</span>
                          <span style={{ fontSize:11, color:'var(--accent-gold)', marginLeft:'auto' }}>
                            💰 {snap.protagonist_points} pt · {snap.protagonist_tier}★
                          </span>
                        </div>
                        {userMsg && (
                          <div style={{ fontSize:12, color:'var(--text-secondary)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                            🗨 {userMsg.preview}
                          </div>
                        )}
                      </div>
                      <button
                        className="btn btn-ghost btn-sm"
                        style={{ color:'var(--accent-rose)', flexShrink:0, fontSize:11, marginTop:2 }}
                        onClick={() => handleTurnRollback(snap)}
                        disabled={!!turnRollbacking}
                        title="回退到此快照（恢复积分/XP/记忆）"
                      >
                        {turnRollbacking === snap.snapshot_id
                          ? <span className="spinner" style={{ width:10, height:10 }} />
                          : '⏪ 回退'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}