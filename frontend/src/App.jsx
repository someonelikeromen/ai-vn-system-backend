import { useState, useRef, useEffect } from 'react';
import './index.css';
import './App.css';
import { useGame, useNovel } from './hooks/useGame.js';
import LeftPanel from './components/LeftPanel.jsx';
import CenterPanel from './components/CenterPanel.jsx';
import RightPanel from './components/RightPanel.jsx';
import ExchangeModal from './components/ExchangeModal.jsx';
import { NovelPickerModal, ChapterModal } from './components/NovelModals.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import ProtagonistGeneratorModal from './components/ProtagonistGeneratorModal.jsx';
import RollbackModal from './components/RollbackModal.jsx';
import { api } from './api.js';

export default function App() {
  // ── 小说 & 主角状态 ─────────────────────────────
  const { novels, novel, protagonist, hooks, loading: novelLoading,
          loadNovels, selectNovel, refreshProtagonist, setHooks } = useNovel();
  const [novelId, setNovelId] = useState('');

  // ── 游戏回合 ─────────────────────────────────────
  const {
    messages, isStreaming, logEvents, grants, currentStep,
    sendMessage, abort, setChapterId, loadMessages,
  } = useGame(novelId);

  // ── UI 状态 ──────────────────────────────────────
  const [input, setInput]               = useState('');
  const [showPicker, setShowPicker]     = useState(false);
  const [showExchange, setShowExchange] = useState(false);
  const [showChapter, setShowChapter]   = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showGenModal, setShowGenModal] = useState(false);
  const [showRollback, setShowRollback] = useState(false);
  const [backendOk, setBackendOk]       = useState(null);
  const inputRef = useRef(null);

  // ── 后端健康检查 ─────────────────────────────────
  useEffect(() => {
    api.health()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  // ── 选择小说 ─────────────────────────────────────
  const handleSelectNovel = async (id) => {
    setNovelId(id);
    await selectNovel(id);
  };

  // ── 发送消息 ─────────────────────────────────────
  const handleSend = () => {
    if (!novelId) { setShowPicker(true); return; }
    if (!input.trim() || isStreaming) return;
    sendMessage(input.trim());
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === 'Escape' && isStreaming) abort();
  };

  // 兑换成功后刷新主角
  const handlePurchased = async () => {
    if (novelId) await refreshProtagonist(novelId);
  };

  // 章节固化后刷新 hooks，并将新 chapter_id 传给游戏引擎
  const handleAnchored = async (res) => {
    if (!novelId) return;
    // 将新 chapter_id 传给 SSE 引擎，后续消息归档到正确章节
    if (res?.chapter_id) {
      setChapterId(res.chapter_id);
    }
    const { hooks: h } = await api.getHooks(novelId).catch(() => ({ hooks: [] }));
    setHooks(h || []);
  };

  const canSend = !!novelId && !!protagonist && !isStreaming && input.trim().length > 0;

  return (
    <>
      {/* ── Header ──────────────────────────────── */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-brand-icon">⚔</div>
          <span className="header-brand-title">零度叙事系统</span>
          {novel && (
            <span className="header-novel-name">{novel.title ?? '未命名'}</span>
          )}
        </div>

        {/* 状态指示 */}
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          {backendOk === true && <span className="badge badge-green">● 后端在线</span>}
          {backendOk === false && (
            <span className="badge badge-rose" title="请启动 start.bat">● 后端离线</span>
          )}
          {backendOk === null && <span className="badge" style={{ background:'rgba(255,255,255,0.05)', color:'var(--text-dim)' }}>检测中…</span>}
        </div>

        <div className="header-actions">
          {novelId && (
            <>
              {/* 当前世界显示 + 切换 */}
              {novel?.current_world_key && (
                <span className="badge badge-blue" style={{ cursor:'default', userSelect:'none' }}
                  title={`当前世界: ${novel.current_world_key}`}>
                  🌐 {novel.current_world_key}
                </span>
              )}
              <button className="btn btn-ghost btn-sm" onClick={() => setShowChapter(true)} title="固化章节">
                📌 固化章节
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowRollback(true)}
                title="回退到上一快照"
                style={{ color: 'var(--accent-rose)', borderColor: 'rgba(244,63,94,0.35)' }}
              >
                ⏪ 回退
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowExchange(true)} title="兑换系统">
                🛒 兑换
              </button>
              {/* 主角未初始化时显示 AI 生成入口 */}
              {!protagonist && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setShowGenModal(true)}
                  title="AI 生成主角"
                  style={{ background:'rgba(124,58,237,0.15)', borderColor:'rgba(124,58,237,0.4)', color:'#a78bfa' }}
                >
                  ✨ 生成主角
                </button>
              )}
            </>
          )}
          <a
            href="/test.html"
            target="_blank"
            rel="noopener"
            className="btn btn-ghost btn-sm"
            title="打开测试控制台"
            style={{ fontSize:12, padding:'4px 10px', textDecoration:'none', color:'var(--accent-green)' }}
          >
            🧪 测试
          </a>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setShowSettings(true)}
            title="模型配置"
            style={{ fontSize:16, padding:'4px 10px' }}
          >
            ⚙️
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowPicker(true)}
          >
            📚 {novel ? (novel.title ?? '未命名').slice(0, 8) + '…' : '选择小说'}
          </button>
        </div>
      </header>

      {/* ── Main 三栏 ────────────────────────────── */}
      <main className="app-main">
        {/* 左栏 - Agent日志 */}
        <LeftPanel
          novelId={novelId}
          logEvents={logEvents}
          currentStep={currentStep}
          isStreaming={isStreaming}
        />

        {/* 中栏 - 正文 */}
        <CenterPanel
          messages={messages}
          isStreaming={isStreaming}
          novel={novel}
        />

        {/* 输入区 */}
        <div className="glass-panel panel-input">
          <div className="input-wrapper" style={{ flex: 1 }}>
            <input
              ref={inputRef}
              id="main-input"
              className="main-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                !novelId ? '选择小说后开始输入行动…' :
                !protagonist ? '初始化主角后开始…' :
                isStreaming ? '系统处理中，按 Esc 可中止…' :
                '输入主角行动（Enter 发送，Shift+Enter 换行）'
              }
              disabled={isStreaming || !novelId || !protagonist}
              autoComplete="off"
              maxLength={500}
            />
            {input.length > 200 && (
              <span className="input-hint">{input.length}/500</span>
            )}
          </div>

          {isStreaming ? (
            <button className="btn btn-danger" onClick={abort} title="中止当前回合">
              ⏹ 中止
            </button>
          ) : (
            <button
              className="btn btn-primary"
              onClick={handleSend}
              disabled={!canSend}
              title={!novelId ? '请先选择小说' : ''}
            >
              发送 ▶
            </button>
          )}
        </div>

        {/* 右栏 - 角色面板 */}
        <RightPanel
          novelId={novelId}
          novel={novel}
          protagonist={protagonist}
          hooks={hooks}
          onOpenExchange={() => setShowExchange(true)}
          onRefresh={() => novelId && refreshProtagonist(novelId)}
        />
      </main>

      {/* ── 赠品条通知（最新N条） ───────────────── */}
      {grants.length > 0 && (
        <div style={{
          position:'fixed', bottom:90, right:290, zIndex:100,
          display:'flex', flexDirection:'column', gap:4,
          maxWidth: 280,
        }}>
          {grants.slice(-3).map((g, i) => (
            <div key={i} className="grant-bar anim-in">
              <span className="grant-icon">✨</span>
              <span className="grant-text">{formatGrant(g)}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Modals ───────────────────────────────── */}
      {showPicker && (
        <NovelPickerModal
          novels={novels}
          currentNovelId={novelId}
          onSelect={handleSelectNovel}
          onClose={() => setShowPicker(false)}
          onCreated={async (id) => {
            await loadNovels();
            await handleSelectNovel(id);
          }}
          onListChanged={async () => {
            await loadNovels();
          }}
        />
      )}
      {showExchange && novelId && (
        <ExchangeModal
          novelId={novelId}
          onClose={() => setShowExchange(false)}
          onPurchased={handlePurchased}
        />
      )}
      {showChapter && novelId && (
        <ChapterModal
          novelId={novelId}
          onClose={() => setShowChapter(false)}
          onAnchored={handleAnchored}
        />
      )}
      {showSettings && (
        <SettingsModal onClose={() => setShowSettings(false)} />
      )}
      {showRollback && novelId && (
        <RollbackModal
          novelId={novelId}
          onClose={() => setShowRollback(false)}
          onRollback={async () => {
            await loadMessages();
            if (novelId) await refreshProtagonist(novelId);
          }}
        />
      )}
      {showGenModal && novelId && (
        <ProtagonistGeneratorModal
          novelId={novelId}
          onClose={() => setShowGenModal(false)}
          onGenerated={async () => {
            await refreshProtagonist(novelId);
            setShowGenModal(false);
          }}
        />
      )}
    </>
  );
}

function formatGrant(g) {
  switch (g.type) {
    case 'kill':   return `击${g.kill_type === 'kill' ? '杀' : '败'} ${g.tier}★${g.tier_sub} 敌人`;
    case 'xp':     return `${g.school} 经验 +${g.amount}`;
    case 'points': return `积分 +${g.amount}`;
    case 'stat':   return `${g.attr} ${g.delta >= 0 ? '+' : ''}${g.delta}`;
    case 'energy': return `${g.pool} ${g.delta}`;
    default:       return g.type;
  }
}
