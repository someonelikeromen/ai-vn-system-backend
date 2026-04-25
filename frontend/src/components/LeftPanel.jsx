import { useState, useEffect, useRef } from 'react';
import { api } from '../api.js';

const STEPS = [
  { id: 0, label: 'STEP 0 · 状态读取', icon: '📖' },
  { id: 1, label: 'STEP 1 · 一致性验证', icon: '🔍' },
  { id: 2, label: 'STEP 2 · 世界推演', icon: '🌐' },
  { id: 3, label: 'STEP 3 · 正文创作', icon: '✍️' },
  { id: 4, label: 'STEP 4 · 归档结算', icon: '📊' },
];

const LOG_ICONS = { log: '', thought: '💭', grant: '💎', error: '⚠️', done: '✓' };

const NODE_TYPE_COLORS = {
  character:    '#a78bfa',
  event:        '#60a5fa',
  world_lore:   '#34d399',
  item:         '#fbbf24',
  relationship: '#f472b6',
  chapter_summary: '#94a3b8',
  concept:      '#fb923c',
};

const NODE_TYPE_LABELS = {
  character: '角色',
  event: '事件',
  world_lore: '世界常识',
  item: '物品',
  relationship: '关系',
  chapter_summary: '章节总结',
  concept: '概念',
};

// Agent 元数据配置
const AGENT_META = {
  dm:          { label: 'DM · 世界主',     icon: '🎲', color: '#60a5fa',  step: 'STEP 1' },
  npc:         { label: 'NPC · 角色行为',  icon: '🎭', color: '#f472b6',  step: 'STEP 2' },
  sandbox:     { label: 'Sandbox · 沙盒',  icon: '⚗️', color: '#34d399',  step: 'STEP 2' },
  style:       { label: 'StyleDirector',   icon: '🎨', color: '#fb923c',  step: 'STEP 3' },
  chronicler:  { label: 'Chronicler · 书记员', icon: '✍️', color: '#a78bfa', step: 'STEP 3' },
  calibrator:  { label: 'Calibrator · 校准', icon: '⚖️', color: '#fbbf24', step: 'STEP 4' },
  planner:     { label: 'Planner · 规划师', icon: '🗺️', color: '#94a3b8', step: 'STEP 4' },
};

export default function LeftPanel({ novelId, logEvents, currentStep, isStreaming }) {
  const [tab, setTab] = useState('log');          // 'log' | 'agents' | 'memory'
  const [memStats, setMemStats]   = useState(null);
  const [memNodes, setMemNodes]   = useState([]);
  const [memLoading, setMemLoading] = useState(false);
  const [typeFilter, setTypeFilter] = useState('');
  const [recallQuery, setRecallQuery] = useState('');
  const [recallResult, setRecallResult] = useState(null);
  const [recalling, setRecalling] = useState(false);
  const bodyRef = useRef(null);

  // 自动滚动到底部（日志 tab）
  useEffect(() => {
    if (tab === 'log' && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [logEvents, tab]);

  // 切换到记忆 Tab 时自动加载
  useEffect(() => {
    if (tab === 'memory' && novelId) {
      loadMemory();
    }
  }, [tab, novelId, typeFilter]);

  // 切换小说时重置记忆数据
  useEffect(() => {
    setMemStats(null);
    setMemNodes([]);
  }, [novelId]);

  const loadMemory = async () => {
    if (!novelId) return;
    setMemLoading(true);
    try {
      const res = await api.getMemoryNodes(novelId, typeFilter, '', 40);
      setMemStats(res.stats || null);
      setMemNodes(res.nodes || []);
    } catch { /* ignore */ }
    finally { setMemLoading(false); }
  };

  const handleRecall = async () => {
    if (!novelId || !recallQuery.trim()) return;
    setRecalling(true);
    try {
      const res = await api.manualRecall(novelId, { query: recallQuery, top_k: 10 });
      setRecallResult(res);
    } catch (e) {
      setRecallResult({ core_count: 0, recalled_count: 0, error: e.message, result: {} });
    } finally { setRecalling(false); }
  };

  // 从 logEvents 中提取 thought 类型的事件，按 agent 分组
  const agentThoughts = (() => {
    const groups = {}; // agent -> [{id, content, ts}]
    logEvents.forEach(e => {
      if (e.type === 'thought' && e.agent) {
        if (!groups[e.agent]) groups[e.agent] = [];
        groups[e.agent].push(e);
      }
    });
    return groups;
  })();

  const nodeTypes = Object.keys(NODE_TYPE_COLORS);

  const TABS = [
    ['log',    '🤖 日志'],
    ['agents', '💬 Agent回复'],
    ['memory', '🧠 记忆图谱'],
  ];

  return (
    <div className="glass-panel panel-left" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

      {/* Tab 切换 */}
      <div style={{ display:'flex', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
        {TABS.map(([id, label]) => (
          <button key={id}
            onClick={() => setTab(id)}
            style={{
              flex:1, padding:'7px 2px', border:'none', cursor:'pointer', background:'transparent',
              color: tab === id ? 'var(--accent-blue)' : 'var(--text-secondary)',
              fontSize:10, fontWeight: tab === id ? 600 : 400,
              borderBottom: tab === id ? '2px solid var(--accent-blue)' : '2px solid transparent',
              fontFamily:'var(--font-ui)',
            }}
          >{label}</button>
        ))}
      </div>

      {/* ──────── 日志 Tab ──────── */}
      {tab === 'log' && (
        <>
          {/* 日志标题 */}
          <div className="agent-log-header">
            <div className="agent-log-title">
              <span className="dot" style={{ display: isStreaming ? 'block' : 'none' }} />
              <span>Agent 日志</span>
            </div>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
              {logEvents.length} 条
            </span>
          </div>

          {/* 日志条目 */}
          <div className="agent-log-body" ref={bodyRef}>
            {logEvents.length === 0 && (
              <div style={{ color: 'var(--text-dim)', fontSize: 12, textAlign: 'center', marginTop: 20 }}>
                等待开始新回合…
              </div>
            )}
            {logEvents.map(e => (
              <LogEntry key={e.id} entry={e} />
            ))}
          </div>

          {/* STEP 进度指示器 */}
          <div className="step-indicators">
            <div className="section-title" style={{ marginBottom: 6, borderBottom: 'none', paddingBottom: 0 }}>
              工作流进度
            </div>
            {STEPS.map(step => {
              const isDone   = currentStep > step.id;
              const isActive = currentStep === step.id && isStreaming;
              return (
                <div
                  key={step.id}
                  className={`step-item ${isActive ? 'active' : ''} ${isDone ? 'done' : ''}`}
                >
                  <div className="step-indicator">
                    {isDone ? '✓' : isActive ? <span className="spinner" style={{ width: 8, height: 8, borderWidth: 1.5 }} /> : step.id}
                  </div>
                  <span>{step.icon} {step.label}</span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ──────── Agent 回复 Tab ──────── */}
      {tab === 'agents' && (
        <div style={{ flex:1, overflowY:'auto', padding:'8px 8px', display:'flex', flexDirection:'column', gap:6 }}>
          {Object.keys(agentThoughts).length === 0 && (
            <div style={{ color:'var(--text-dim)', fontSize:12, textAlign:'center', paddingTop:24, lineHeight:1.8 }}>
              💬 尚无 Agent 回复<br />
              <span style={{ fontSize:10 }}>发起一次行动后，各 Agent 的思考与回复将在此展示</span>
            </div>
          )}
          {/* 按照 AGENT_META 定义的顺序渲染，未知 agent 追加到末尾 */}
          {[...Object.keys(AGENT_META), ...Object.keys(agentThoughts).filter(k => !AGENT_META[k])]
            .filter(agent => agentThoughts[agent]?.length > 0)
            .map(agent => (
              <AgentThoughtCard
                key={agent}
                agent={agent}
                thoughts={agentThoughts[agent]}
              />
            ))}
        </div>
      )}

      {/* ──────── 记忆图谱 Tab ──────── */}
      {tab === 'memory' && (
        <div style={{ flex:1, overflow:'hidden', display:'flex', flexDirection:'column' }}>
          {/* 统计卡 */}
          {memStats && (
            <div style={{ padding:'8px 10px', background:'rgba(255,255,255,0.02)', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
              <div style={{ display:'flex', gap:12, fontSize:11 }}>
                <span style={{ color:'var(--accent-blue)' }}>📊 节点: {memStats.total_nodes}</span>
                <span style={{ color:'var(--text-secondary)' }}>关系: {memStats.total_edges}</span>
              </div>
              {memStats.by_type && (
                <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginTop:4 }}>
                  {Object.entries(memStats.by_type).map(([t, cnt]) => (
                    <span key={t} style={{
                      fontSize:9, padding:'1px 5px', borderRadius:3,
                      background:`${NODE_TYPE_COLORS[t] || '#888'}22`,
                      color: NODE_TYPE_COLORS[t] || 'var(--text-dim)',
                      border:`1px solid ${NODE_TYPE_COLORS[t] || '#888'}44`,
                    }}>{NODE_TYPE_LABELS[t] || t}: {cnt}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 类型过滤 + 刷新 */}
          <div style={{ display:'flex', gap:6, padding:'6px 10px', flexShrink:0, borderBottom:'1px solid var(--border)' }}>
            <select
              className="settings-select"
              style={{ flex:1, fontSize:11, padding:'3px 6px' }}
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
            >
              <option value="">全部类型</option>
              {nodeTypes.map(t => <option key={t} value={t}>{NODE_TYPE_LABELS[t] || t}</option>)}
            </select>
            <button
              className="btn btn-ghost btn-sm"
              style={{ fontSize:10, padding:'3px 8px', flexShrink:0 }}
              onClick={loadMemory}
              disabled={memLoading}
            >{memLoading ? <span className="spinner" style={{width:8,height:8}} /> : '🔄'}</button>
          </div>

          {/* 节点列表 */}
          <div style={{ flex:1, overflowY:'auto', padding:'6px 8px', display:'flex', flexDirection:'column', gap:4 }}>
            {!novelId && (
              <div style={{ textAlign:'center', color:'var(--text-dim)', fontSize:12, paddingTop:20 }}>请先选择小说</div>
            )}
            {novelId && !memLoading && memNodes.length === 0 && (
              <div style={{ textAlign:'center', color:'var(--text-dim)', fontSize:12, paddingTop:20 }}>
                暂无记忆节点<br />
                <span style={{ fontSize:10 }}>完成几轮对话后图谱将自动填充</span>
              </div>
            )}
            {memLoading && (
              <div style={{ display:'flex', justifyContent:'center', paddingTop:20 }}>
                <span className="spinner" style={{width:16,height:16}} />
              </div>
            )}
            {memNodes.map((node, i) => {
              const color = NODE_TYPE_COLORS[node.node_type] || '#888';
              return (
                <div key={node.node_id || i} style={{
                  background:`${color}0a`, borderLeft:`2px solid ${color}`,
                  borderRadius:4, padding:'5px 8px', fontSize:11,
                }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:2 }}>
                    <span style={{ color, fontWeight:600, fontSize:10 }}>{NODE_TYPE_LABELS[node.node_type] || node.node_type}</span>
                    <span style={{ color:'var(--text-dim)', fontSize:9 }}>{node.created_at?.slice(0,10)}</span>
                  </div>
                  <div style={{ color:'var(--text-primary)', lineHeight:1.4 }}>
                    {(node.label || node.content || node.node_id || '').slice(0, 80)}
                    {(node.label || node.content || '').length > 80 ? '…' : ''}
                  </div>
                  {node.world_key && (
                    <div style={{ fontSize:9, color:'var(--accent-blue)', marginTop:2 }}>🌐 {node.world_key}</div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 手动记忆召回 */}
          <div style={{ padding:'6px 10px', borderTop:'1px solid var(--border)', flexShrink:0 }}>
            <div style={{ fontSize:10, color:'var(--text-dim)', marginBottom:4 }}>🔍 手动叫堆记忆</div>
            <div style={{ display:'flex', gap:4 }}>
              <input
                className="input-field"
                style={{ flex:1, fontSize:11, padding:'3px 8px', height:28 }}
                placeholder="输入查询词…"
                value={recallQuery}
                onChange={e => setRecallQuery(e.target.value)}
                onKeyDown={e => e.key==='Enter' && handleRecall()}
              />
              <button
                className="btn btn-ghost btn-sm"
                style={{ fontSize:10, padding:'3px 8px', flexShrink:0 }}
                onClick={handleRecall}
                disabled={recalling || !recallQuery.trim()}
              >{recalling ? <span className="spinner" style={{width:8,height:8}} /> : '召回'}</button>
            </div>
            {recallResult && (
              <div style={{ marginTop:6, fontSize:10, color:'var(--text-secondary)' }}>
                核心: {recallResult.core_count} 条 · 其他: {recallResult.recalled_count} 条
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ fontSize:9, padding:'1px 5px', marginLeft:6 }}
                  onClick={() => setRecallResult(null)}
                >清除</button>
                {recallResult.result?.recalled?.slice(0,5).map((n,i) => (
                  <div key={i} style={{ marginTop:3, background:'rgba(255,255,255,0.03)', borderRadius:3, padding:'2px 6px' }}>
                    <span style={{ color:NODE_TYPE_COLORS[n.node_type]||'#888', fontSize:9 }}>[{NODE_TYPE_LABELS[n.node_type] || n.node_type}]</span>
                    {' '}{(n.label||n.content||'').slice(0,60)}…
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}

// ── Agent 回复卡片（按 agent 分组，显示最新一条，可展开历史） ──
function AgentThoughtCard({ agent, thoughts }) {
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll]   = useState(false);

  const meta = AGENT_META[agent] || { label: agent, icon: '🤖', color: '#888', step: '' };
  // 最新的思考记录排在最前
  const sorted = [...thoughts].reverse();
  const latest = sorted[0];
  const rest   = sorted.slice(1);

  const fullText = latest?.content || '';

  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${meta.color}33`,
      background: `${meta.color}0a`,
      overflow: 'hidden',
      transition: 'box-shadow 0.2s',
    }}>
      {/* 头部：点击展开/收起最新内容 */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          padding: '8px 10px',
          cursor: 'pointer',
          borderBottom: expanded ? `1px solid ${meta.color}22` : 'none',
          userSelect: 'none',
        }}
      >
        <span style={{ fontSize: 15, flexShrink: 0 }}>{meta.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>{meta.label}</span>
            {meta.step && (
              <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 4 }}>{meta.step}</span>
            )}
          </div>
          {/* 预览第一行（折叠时） */}
          {!expanded && (
            <div style={{
              fontSize: 10, color: 'var(--text-secondary)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              marginTop: 2,
            }}>
              {fullText.slice(0, 60)}{fullText.length > 60 ? '…' : ''}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          {thoughts.length > 1 && (
            <span style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 10,
              background: `${meta.color}22`, color: meta.color, fontWeight: 600,
            }}>×{thoughts.length}</span>
          )}
          <span style={{
            fontSize: 9, color: 'var(--text-dim)',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s', display: 'inline-block',
          }}>▼</span>
        </div>
      </div>

      {/* 展开区：显示最新完整内容 */}
      {expanded && (
        <div style={{ padding: '8px 10px' }}>
          <div style={{
            fontSize: 11, color: 'var(--text-primary)',
            lineHeight: 1.7, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            maxHeight: 320, overflowY: 'auto',
            scrollbarWidth: 'thin',
          }}>
            {fullText || '（无内容）'}
          </div>

          {/* 历史条目（同 agent 多次思考） */}
          {rest.length > 0 && (
            <div style={{ marginTop: 8, borderTop: `1px solid ${meta.color}22`, paddingTop: 6 }}>
              <button
                onClick={e => { e.stopPropagation(); setShowAll(v => !v); }}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: meta.color, fontSize: 10, padding: '2px 0',
                }}
              >
                {showAll ? '▲ 收起历史' : `▼ 查看更早的 ${rest.length} 条记录`}
              </button>
              {showAll && rest.map((entry, i) => (
                <div key={entry.id || i} style={{
                  marginTop: 6, padding: '6px 8px',
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: 5,
                  fontSize: 10, color: 'var(--text-secondary)',
                  lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  maxHeight: 160, overflowY: 'auto',
                }}>
                  <div style={{ fontSize: 9, color: 'var(--text-dim)', marginBottom: 3 }}>
                    历史记录 #{rest.length - i}
                  </div>
                  {entry.content}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LogEntry({ entry }) {
  const [expanded, setExpanded] = useState(false);

  // 是否有完整内容可展开
  const fullContent = entry.content || '';
  const isLong = fullContent.length > 100;
  const canExpand = isLong || entry.type === 'thought';

  const BORDER_COLORS = {
    log:     'var(--accent-blue)',
    thought: 'var(--accent-purple)',
    grant:   'var(--accent-gold)',
    error:   'var(--accent-rose)',
    done:    'var(--accent-green)',
  };
  const borderColor = BORDER_COLORS[entry.type] || 'var(--border)';

  const TYPE_BG = {
    log:     'rgba(79,156,249,0.04)',
    thought: 'rgba(124,58,237,0.06)',
    grant:   'rgba(251,191,36,0.06)',
    error:   'rgba(244,63,94,0.08)',
    done:    'rgba(52,211,153,0.06)',
  };
  const bg = TYPE_BG[entry.type] || 'transparent';

  const handleClick = () => { if (canExpand) setExpanded(e => !e); };

  const preview = isLong && !expanded
    ? fullContent.slice(0, 100) + '…'
    : fullContent;

  return (
    <div
      onClick={handleClick}
      style={{
        borderLeft: `2px solid ${borderColor}`,
        background: bg,
        borderRadius: '0 5px 5px 0',
        padding: '5px 8px 5px 10px',
        marginBottom: 3,
        cursor: canExpand ? 'pointer' : 'default',
        transition: 'background 0.15s',
        userSelect: expanded ? 'text' : 'none',
      }}
    >
      {/* 头部行：badge + 首行内容 + 展开图标 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 5 }}>
        {/* 类型标识 */}
        <span style={{
          fontSize: 9, fontWeight: 700, flexShrink: 0, marginTop: 1,
          color: borderColor, letterSpacing: '0.04em',
        }}>
          {entry.type === 'log'     && `S${entry.step ?? '?'}`}
          {entry.type === 'thought' && (entry.agent ? `[${entry.agent}]` : '💭')}
          {entry.type === 'grant'   && '💎'}
          {entry.type === 'error'   && '⚠️'}
          {entry.type === 'done'    && '✓✓'}
        </span>

        {/* 内容文本 */}
        <span style={{
          flex: 1,
          fontSize: 11,
          color: entry.type === 'error' ? 'var(--accent-rose)'
               : entry.type === 'done'  ? 'var(--accent-green)'
               : entry.type === 'grant' ? 'var(--accent-gold)'
               : 'var(--text-secondary)',
          lineHeight: 1.55,
          wordBreak: 'break-all',
          whiteSpace: expanded ? 'pre-wrap' : 'normal',
        }}>
          {preview}
        </span>

        {/* 展开/收起箭头 */}
        {canExpand && (
          <span style={{
            flexShrink: 0, fontSize: 9, color: 'var(--text-dim)',
            marginTop: 2, transition: 'transform 0.2s',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            display: 'inline-block',
          }}>▼</span>
        )}
      </div>

      {/* 展开区：额外元数据（thought 类型显示 raw payload 调试信息）*/}
      {expanded && entry.type === 'thought' && entry.agent && (
        <div style={{
          marginTop: 4, paddingTop: 4,
          borderTop: '1px solid rgba(255,255,255,0.06)',
          fontSize: 10, color: 'var(--text-dim)',
          display: 'flex', gap: 8,
        }}>
          <span>Agent: <span style={{ color: 'var(--accent-purple)' }}>{entry.agent}</span></span>
          <span>字数: {fullContent.length}</span>
        </div>
      )}
    </div>
  );
}
