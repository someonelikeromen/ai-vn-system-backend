import { useState, useEffect } from 'react';
import { api } from '../api.js';

const ITEM_ICONS = {
  ApplicationTechnique: '⚡', PassiveAbility: '🔮',
  PowerSource: '💠', Bloodline: '🩸', Mech: '🤖',
  Inventory: '🎒', Companion: '👥', Knowledge: '📚', WorldTraverse: '🌀',
};
const ITEM_LABELS = {
  ApplicationTechnique: '应用技巧', PassiveAbility: '被动能力',
  PowerSource: '力量基盘', Bloodline: '血统体质', Mech: '机甲',
  Inventory: '物品装备', Companion: '同伴', Knowledge: '知识理论', WorldTraverse: '世界坐标',
};
const ATTR_LABELS = {
  STR:'力量', DUR:'耐力', VIT:'体质', REC:'恢复',
  AGI:'敏捷', REF:'反应', PER:'感知', MEN:'精神', SOL:'灵魂', CHA:'魅力',
};

const REWARD_ICONS = { points:'💎', medal:'⭐', unlock:'🔓', item:'📦', '' : '' };

export default function RightPanel({ novelId, novel, protagonist, hooks, onOpenExchange, onRefresh }) {
  const [activeTab, setActiveTab] = useState('stat'); // 'stat'|'items'|'hooks'|'achievements'|'relations'
  const [achievements, setAchievements] = useState([]);
  const [achLoaded, setAchLoaded] = useState(false);
  const [worldArchive, setWorldArchive] = useState(null);
  const [worldExpanded, setWorldExpanded] = useState(false);
  const [worldLoading, setWorldLoading] = useState(false);
  // 人际关系
  const [npcs, setNpcs] = useState([]);
  const [npcLoaded, setNpcLoaded] = useState(false);
  const [npcLoading, setNpcLoading] = useState(false);

  const currentWorldKey = novel?.current_world_key || '';

  // 切换成就 Tab 时懒加载
  useEffect(() => {
    if (activeTab === 'achievements' && novelId && !achLoaded) {
      api.getAchievements(novelId)
        .then(r => { setAchievements(r.achievements || []); setAchLoaded(true); })
        .catch(() => {});
    }
  }, [activeTab, novelId, achLoaded]);

  // 世界档案懒加载
  const loadWorldArchive = async () => {
    if (!novelId || !currentWorldKey || worldLoading) return;
    setWorldLoading(true);
    try {
      const res = await api.getWorldArchive(novelId, currentWorldKey);
      setWorldArchive(res.archive || null);
    } catch { setWorldArchive(null); }
    finally { setWorldLoading(false); }
  };

  // 切换小说时重置世界档案和成就缓存
  useEffect(() => {
    setAchLoaded(false);
    setAchievements([]);
    setWorldArchive(null);
    setWorldExpanded(false);
    setNpcLoaded(false);
    setNpcs([]);
  }, [novelId]);

  // 切换到关系 Tab 时懒加载 NPC
  useEffect(() => {
    if (activeTab === 'relations' && novelId && !npcLoaded && !npcLoading) {
      setNpcLoading(true);
      api.getNpcs(novelId)
        .then(r => { setNpcs(r.npcs || []); setNpcLoaded(true); })
        .catch(() => {})
        .finally(() => setNpcLoading(false));
    }
  }, [activeTab, novelId, npcLoaded, npcLoading]);

  if (!protagonist) {
    return (
      <div className="glass-panel panel-right" style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:10, color:'var(--text-dim)', padding:20 }}>
        <div style={{ fontSize: 32 }}>👤</div>
        <div style={{ fontSize: 13, textAlign: 'center' }}>
          请先选择小说<br />并初始化主角
        </div>
      </div>
    );
  }

  const { protagonist: p, owned_items = [], medals = {}, points = 0 } = protagonist;
  const attrs = p?.attributes || {};
  const energyPools = p?.energy_pools || {};
  const statusEffects = p?.status_effects || [];

  const tabs = [
    { id: 'stat',         label: '状态' },
    { id: 'items',        label: `物品(${owned_items.length})` },
    { id: 'hooks',        label: `伏笔(${hooks.length})` },
    { id: 'achievements', label: `🏆(${achievements.length})` },
    { id: 'relations',    label: `🔗关系` },
  ];

  return (
    <div className="glass-panel panel-right" style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {/* Tab 栏 */}
      <div style={{ display:'flex', borderBottom:'1px solid var(--border)', flexShrink: 0 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            style={{
              flex: 1, padding: '10px 4px', border: 'none', cursor: 'pointer',
              background: activeTab === t.id ? 'rgba(79,156,249,0.1)' : 'transparent',
              color: activeTab === t.id ? 'var(--accent-blue)' : 'var(--text-secondary)',
              fontSize: 11, fontWeight: activeTab === t.id ? 600 : 400,
              borderBottom: activeTab === t.id ? '2px solid var(--accent-blue)' : '2px solid transparent',
              transition: 'all 0.2s', fontFamily: 'var(--font-ui)',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="char-sheet-body">

        {/* ── 状态页 ── */}
        {activeTab === 'stat' && (
          <StatTab
            p={p} points={points} medals={medals}
            attrs={attrs} energyPools={energyPools} statusEffects={statusEffects}
            currentWorldKey={currentWorldKey}
            worldArchive={worldArchive} worldExpanded={worldExpanded}
            worldLoading={worldLoading}
            onWorldToggle={() => { setWorldExpanded(e => !e); if (!worldArchive && !worldExpanded) loadWorldArchive(); }}
            onOpenExchange={onOpenExchange} onRefresh={onRefresh}
          />
        )}

        {/* ── 物品页 ── */}
        {activeTab === 'items' && (
          <ItemsTab items={owned_items} onOpenExchange={onOpenExchange} />
        )}

        {/* ── 人际关系页 ── */}
        {activeTab === 'relations' && (
          <RelationsTab npcs={npcs} loading={npcLoading} />
        )}

        {/* ── 伏笔页 ── */}
        {activeTab === 'hooks' && (
          <>
            <div className="section-title">活跃伏笔 ({hooks.filter(h=>h.status==='active').length})</div>
            {hooks.filter(h => h.status === 'active').length === 0 ? (
              <div style={{ color: 'var(--text-dim)', fontSize: 12, textAlign: 'center', padding: '20px 0' }}>
                暂无活跃伏笔
              </div>
            ) : (
              <div className="hook-list">
                {hooks.filter(h => h.status === 'active').map(hook => (
                  <div key={hook.id} className={`hook-item ${hook.urgency || 'low'}`}>
                    <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 2 }}>
                      {hook.urgency === 'high' ? '🔥' : hook.urgency === 'medium' ? '⚡' : '🌱'} {hook.urgency?.toUpperCase()}
                    </div>
                    {hook.description}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ── 成就页 ── */}
        {activeTab === 'achievements' && (
          <>
            <div className="section-title" style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <span>已解锁成就 ({achievements.length})</span>
              <button
                className="btn btn-ghost btn-sm"
                style={{ fontSize:10, padding:'2px 6px' }}
                onClick={() => {
                  setAchLoaded(false);
                  api.getAchievements(novelId)
                    .then(r => { setAchievements(r.achievements || []); setAchLoaded(true); })
                    .catch(() => {});
                }}
              >🔄</button>
            </div>
            {achievements.length === 0 ? (
              <div style={{ textAlign:'center', color:'var(--text-dim)', fontSize:12, padding:'20px 0' }}>
                <div style={{ fontSize:28, marginBottom:8 }}>🏆</div>
                <div>暂无成就</div>
                <div style={{ fontSize:10, marginTop:4, color:'var(--text-dim)' }}>在故事中达成特定目标后自动解锁</div>
              </div>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {achievements.map(ach => (
                  <div key={ach.id} style={{
                    background:'linear-gradient(135deg,rgba(251,191,36,0.06),rgba(251,191,36,0.02))',
                    border:'1px solid rgba(251,191,36,0.25)',
                    borderRadius:8, padding:'10px 12px',
                  }}>
                    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                      <span style={{ fontSize:18 }}>
                        {REWARD_ICONS[ach.reward_type] || '🏆'}
                      </span>
                      <div>
                        <div style={{ fontWeight:700, fontSize:13, color:'var(--accent-gold)' }}>{ach.title}</div>
                        <div style={{ fontSize:10, color:'var(--text-dim)' }}>
                          {ach.unlocked_at?.slice(0,10)} · {ach.achievement_key}
                        </div>
                      </div>
                    </div>
                    {ach.description && (
                      <div style={{ fontSize:11, color:'var(--text-secondary)', lineHeight:1.5 }}>{ach.description}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 状态页完整组件
// ═══════════════════════════════════════════════════════════
const PSYCHE_CAT = { social:'社交', emotional:'情绪', cognitive:'认知', values:'价值观' };
const AXIS_NAMES = {
  introExtro:'内倾←→外倾', trustRadius:'不信任←→信任', dominance:'顺从←→主导',
  empathy:'冷漠←→共情', boundaryStrength:'无边界←→强边界',
  stability:'动荡←→稳定', expressiveness:'压抑←→外放', recoverySpeed:'慢恢复←→快恢复',
  emotionalDepth:'肤浅←→深邃',
  analyticIntuitive:'直觉←→分析', openness:'封闭←→开放', riskTolerance:'规避←→嗜险',
  selfAwareness:'盲区←→自知',
  autonomy:'顺从←→自主', altruism:'利己←→利他', rationality:'情绪←→理性',
  loyalty:'背信←→忠诚', idealism:'现实←→理想',
};

function SectionHeader({ icon, title, count }) {
  return (
    <div style={{ fontSize:11, fontWeight:700, color:'var(--text-secondary)', letterSpacing:'0.05em',
      marginBottom:6, paddingBottom:4, borderBottom:'1px solid var(--border)', marginTop:10 }}>
      {icon} {title}{count != null ? ` (${count})` : ''}
    </div>
  );
}

function PsycheBar({ label, value }) {
  const v = Math.max(-10, Math.min(10, value || 0));
  const pct = ((v + 10) / 20) * 100;
  const color = v > 3 ? 'var(--accent-blue)' : v < -3 ? 'var(--accent-purple)' : 'var(--text-dim)';
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
      <span style={{ fontSize:10, color:'var(--text-dim)', width:120, flexShrink:0 }}>{AXIS_NAMES[label] || label}</span>
      <div style={{ flex:1, height:4, background:'rgba(255,255,255,0.08)', borderRadius:2, position:'relative' }}>
        <div style={{ position:'absolute', left:'50%', top:0, width:1, height:'100%', background:'var(--border)' }} />
        <div style={{ position:'absolute', left:`${pct}%`, top:-2, width:8, height:8,
          borderRadius:'50%', background:color, transform:'translateX(-50%)', boxShadow:`0 0 4px ${color}` }} />
      </div>
      <span style={{ fontSize:10, color, width:20, textAlign:'right', flexShrink:0 }}>{v > 0 ? '+' : ''}{v}</span>
    </div>
  );
}

function StatTab({ p, points, medals, attrs, energyPools, statusEffects,
  currentWorldKey, worldArchive, worldExpanded, worldLoading,
  onWorldToggle, onOpenExchange, onRefresh }) {

  const [psycheOpen, setPsycheOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(true);

  const psyche = p?.psyche_model_json || {};
  const knowledge = p?.knowledge_scope || [];
  const traits = p?.traits || [];
  const personality = p?.personality || [];
  const flaws = p?.flaws || [];
  const desires = p?.desires || [];
  const fears = p?.fears || [];
  const quirks = p?.quirks || [];

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:0 }}>

      {/* ── 名片 + 积分 ── */}
      <div className="stat-card">
        <div className="stat-card-header">
          <div>
            <div className="stat-char-name">{p?.name || '无名主角'}</div>
            <div style={{ fontSize:11, color:'var(--text-dim)', marginTop:2 }}>
              {[p?.gender, p?.age ? p.age+'岁' : '', p?.identity].filter(Boolean).join(' · ')}
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:4 }}>
            <div className="stat-tier-badge">{p?.tier ?? 0}★{p?.tier_sub ?? 'M'}</div>
            {p?.alignment && <div style={{ fontSize:10, color:'var(--text-dim)' }}>{p.alignment}</div>}
          </div>
        </div>

        {/* 身份标签 */}
        {traits.length > 0 && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:8 }}>
            {traits.map((t, i) => (
              <span key={i} style={{ fontSize:10, background:'rgba(79,156,249,0.15)', color:'var(--accent-blue)',
                borderRadius:4, padding:'1px 6px' }}>{t}</span>
            ))}
          </div>
        )}

        {/* 积分 */}
        <div className="stat-points-row">
          <span className="stat-points-icon">💎</span>
          <span className="stat-points-value">{(points || 0).toLocaleString()}</span>
          <span className="stat-points-label">兑换积分</span>
        </div>

        {/* 凭证 */}
        {Object.keys(medals).length > 0 && (
          <div className="medals-row" style={{ marginBottom: 8 }}>
            {Object.entries(medals).filter(([,v]) => v > 0).map(([stars, cnt]) => (
              <div key={stars} className="medal-chip">⭐{stars}×{cnt}</div>
            ))}
          </div>
        )}

        {/* 属性网格 */}
        {Object.keys(attrs).length > 0 && (
          <div className="attr-grid">
            {Object.entries(attrs).map(([k, v]) => (
              <div key={k} className="attr-cell">
                <span className="attr-key" title={k}>{ATTR_LABELS[k] || k}</span>
                <span className="attr-val">{typeof v === 'number' ? v.toFixed(1) : v}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── 能量池 ── */}
      {Object.keys(energyPools).length > 0 && (
        <>
          <SectionHeader icon="⚡" title="能量池" />
          {Object.entries(energyPools).map(([name, pool]) => {
            const cur = pool?.current ?? 0;
            const max = pool?.max ?? 100;
            const pct = max > 0 ? Math.min(100, Math.round((cur / max) * 100)) : 0;
            const regen = pool?.regen || pool?.description || '';
            return (
              <div key={name} style={{ marginBottom:8 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:3 }}>
                  <span style={{ fontSize:12, fontWeight:600, color:'var(--text-primary)' }}>{name}</span>
                  <span style={{ fontSize:11, color:'var(--accent-gold)', fontWeight:700 }}>{cur} / {max}</span>
                </div>
                <div style={{ height:6, background:'rgba(255,255,255,0.07)', borderRadius:3, overflow:'hidden' }}>
                  <div style={{ height:'100%', width:`${pct}%`, background:'linear-gradient(90deg,var(--accent-blue),var(--accent-purple))',
                    borderRadius:3, transition:'width 0.4s' }} />
                </div>
                {regen && <div style={{ fontSize:10, color:'var(--text-dim)', marginTop:2 }}>↺ {regen}</div>}
              </div>
            );
          })}
        </>
      )}

      {/* ── Buff / Debuff 栏 ── */}
      {statusEffects.length > 0 && (
        <>
          <SectionHeader icon="🔮" title="临时状态" count={statusEffects.length} />
          <div style={{ display:'flex', flexDirection:'column', gap:5, marginBottom:4 }}>
            {statusEffects.map((eff, idx) => {
              const isBuff = eff.type === 'buff' || eff.is_buff;
              const color = isBuff ? 'var(--accent-green)' : 'var(--accent-rose)';
              return (
                <div key={idx} style={{ background:'rgba(255,255,255,0.03)', borderLeft:`2px solid ${color}`,
                  borderRadius:5, padding:'6px 10px', fontSize:12 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', marginBottom:2 }}>
                    <strong style={{ color:'var(--text-primary)' }}>
                      {isBuff ? '▲' : '▼'} {eff.name || '状态异常'}
                    </strong>
                    {eff.duration && <span style={{ fontSize:10, color:'var(--text-dim)' }}>{eff.duration}</span>}
                  </div>
                  <div style={{ color:'var(--text-secondary)', lineHeight:1.5 }}>{eff.effect || eff.description}</div>
                  {eff.value != null && <div style={{ fontSize:10, color }}>效果值：{eff.value > 0 ? '+' : ''}{eff.value}</div>}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── 角色档案（可折叠）── */}
      {(p?.appearance || personality.length > 0 || flaws.length > 0) && (
        <>
          <div onClick={() => setProfileOpen(o => !o)}
            style={{ display:'flex', justifyContent:'space-between', cursor:'pointer',
              fontSize:11, fontWeight:700, color:'var(--text-secondary)', letterSpacing:'0.05em',
              marginBottom: profileOpen ? 6 : 0, paddingBottom:4, borderBottom:'1px solid var(--border)', marginTop:10 }}>
            <span>👤 角色档案</span>
            <span>{profileOpen ? '▲' : '▼'}</span>
          </div>
          {profileOpen && (
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {p?.appearance && (
                <div style={{ fontSize:12, color:'var(--text-secondary)', lineHeight:1.7,
                  background:'rgba(255,255,255,0.02)', borderRadius:6, padding:'6px 8px' }}>
                  <span style={{ fontSize:10, color:'var(--text-dim)', display:'block', marginBottom:2 }}>外貌</span>
                  {p.appearance}
                  {p?.clothing && <span style={{ color:'var(--text-dim)' }}>  |  着装：{p.clothing}</span>}
                </div>
              )}
              {p?.background && (
                <div style={{ fontSize:12, color:'var(--text-secondary)', lineHeight:1.7,
                  background:'rgba(255,255,255,0.02)', borderRadius:6, padding:'6px 8px' }}>
                  <span style={{ fontSize:10, color:'var(--text-dim)', display:'block', marginBottom:2 }}>背景故事</span>
                  {p.background}
                </div>
              )}
              {(personality.length > 0 || flaws.length > 0 || desires.length > 0 || fears.length > 0 || quirks.length > 0) && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
                  {personality.length > 0 && <ProfileList icon="💫" label="性格" items={personality} color="var(--accent-blue)" />}
                  {flaws.length > 0 && <ProfileList icon="⚡" label="缺陷" items={flaws} color="var(--accent-rose)" />}
                  {desires.length > 0 && <ProfileList icon="💎" label="渴望" items={desires} color="var(--accent-gold)" />}
                  {fears.length > 0 && <ProfileList icon="🌑" label="恐惧" items={fears} color="var(--text-dim)" />}
                  {quirks.length > 0 && <ProfileList icon="🔄" label="习惯" items={quirks} color="var(--text-secondary)" />}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── 心理模型（可折叠）── */}
      {psyche.dimensions && (
        <>
          <div onClick={() => setPsycheOpen(o => !o)}
            style={{ display:'flex', justifyContent:'space-between', cursor:'pointer',
              fontSize:11, fontWeight:700, color:'var(--text-secondary)', letterSpacing:'0.05em',
              marginBottom: psycheOpen ? 6 : 0, paddingBottom:4, borderBottom:'1px solid var(--border)', marginTop:10 }}>
            <span>🧠 心理模型</span>
            <span>{psycheOpen ? '▲' : '▼'}</span>
          </div>
          {psycheOpen && (
            <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
              {Object.entries(psyche.dimensions || {}).map(([cat, axes]) => (
                <div key={cat}>
                  <div style={{ fontSize:10, color:'var(--accent-purple)', fontWeight:600, marginBottom:4 }}>
                    {PSYCHE_CAT[cat] || cat}
                  </div>
                  {Object.entries(axes).map(([k, v]) => <PsycheBar key={k} label={k} value={v} />)}
                </div>
              ))}
              {(psyche.triggerPatterns || []).length > 0 && (
                <div>
                  <div style={{ fontSize:10, color:'var(--accent-rose)', fontWeight:600, marginBottom:4 }}>⚠️ 触发模式</div>
                  {psyche.triggerPatterns.map((tp, i) => (
                    <div key={i} style={{ background:'rgba(255,255,255,0.03)', borderRadius:5, padding:'5px 8px',
                      marginBottom:4, fontSize:11 }}>
                      <div style={{ color:'var(--text-dim)' }}>触发：{tp.trigger}</div>
                      <div style={{ color:'var(--text-secondary)' }}>反应：{tp.reaction}</div>
                      <div style={{ color:'var(--accent-rose)', fontSize:10 }}>强度 {tp.intensity}/10</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── 知识图谱 ── */}
      {knowledge.length > 0 && (
        <>
          <SectionHeader icon="📚" title="知识图谱" count={knowledge.length} />
          <div style={{ display:'flex', flexDirection:'column', gap:4, marginBottom:4 }}>
            {knowledge.map((k, i) => (
              <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:11,
                padding:'4px 0', borderBottom:'1px solid rgba(255,255,255,0.04)' }}>
                <span style={{ fontWeight:600, color:'var(--text-primary)', flex:1 }}>
                  {typeof k === 'string' ? k : k.topic}
                </span>
                {k.mastery && <span style={{ fontSize:10, color:'var(--accent-blue)', flexShrink:0 }}>{k.mastery}</span>}
                {k.type && <span style={{ fontSize:9, color:'var(--text-dim)', flexShrink:0 }}>{k.type}</span>}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── 世界档案 ── */}
      {currentWorldKey && (
        <div style={{ marginBottom:8, marginTop:8 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
            cursor:'pointer', padding:'6px 0', borderBottom:'1px solid var(--border)' }}
            onClick={onWorldToggle}>
            <span style={{ fontSize:11, fontWeight:700, color:'var(--accent-blue)' }}>🌐 世界档案 · {currentWorldKey}</span>
            <span style={{ fontSize:11, color:'var(--text-dim)' }}>{worldExpanded ? '▲' : '▼'}</span>
          </div>
          {worldExpanded && (
            <div style={{ background:'rgba(79,156,249,0.04)', border:'1px solid var(--border)',
              borderRadius:6, padding:'8px 10px', fontSize:11, marginTop:4 }}>
              {worldLoading ? (
                <div style={{ display:'flex', justifyContent:'center' }}><span className="spinner" style={{width:12,height:12}} /></div>
              ) : worldArchive ? (
                <>
                  {worldArchive.world_name && <div style={{ color:'var(--text-primary)', fontWeight:600, marginBottom:4 }}>{worldArchive.world_name}</div>}
                  {worldArchive.current_snapshot && typeof worldArchive.current_snapshot === 'string' && (
                    <div style={{ color:'var(--text-secondary)', lineHeight:1.5, marginBottom:4 }}>
                      {worldArchive.current_snapshot.slice(0,200)}{worldArchive.current_snapshot.length>200?'…':''}
                    </div>
                  )}
                  <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                    {worldArchive.time_flow_ratio != null && <span style={{ color:'var(--text-dim)' }}>⏱ 时间流速 ×{worldArchive.time_flow_ratio}</span>}
                    {worldArchive.peak_tier != null && <span style={{ color:'var(--accent-gold)' }}>⭐ 顶点 {worldArchive.peak_tier}★{worldArchive.peak_tier_sub||'M'}</span>}
                  </div>
                </>
              ) : (
                <div style={{ color:'var(--text-dim)' }}>暂无世界档案数据</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── 底部操作 ── */}
      <button className="btn btn-gold btn-lg" onClick={onOpenExchange} style={{ width:'100%', marginTop:8 }}>
        🛒 打开兑换系统
      </button>
      <button className="btn btn-ghost btn-sm" onClick={onRefresh} style={{ width:'100%', marginTop:4 }}>
        🔄 刷新状态
      </button>
    </div>
  );
}

function ProfileList({ icon, label, items, color }) {
  return (
    <div style={{ background:'rgba(255,255,255,0.02)', borderRadius:6, padding:'6px 8px' }}>
      <div style={{ fontSize:10, color:'var(--text-dim)', marginBottom:3 }}>{icon} {label}</div>
      <ul style={{ margin:0, padding:'0 0 0 12px', fontSize:11, color, lineHeight:1.7 }}>
        {items.map((s, i) => <li key={i}>{s}</li>)}
      </ul>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
const ABILITY_TYPES  = new Set(['PassiveAbility', 'ApplicationTechnique', 'PowerSource', 'Bloodline']);
const ITEM_TYPES_SET = new Set(['Inventory', 'Mech']);
const OTHER_TYPES    = new Set(['Companion', 'Knowledge', 'WorldTraverse']);

const CATEGORY_ORDER = [
  { key: 'ability', label: '⚡ 能力 / 技巧', types: ABILITY_TYPES },
  { key: 'item',    label: '🎒 物品 / 装备', types: ITEM_TYPES_SET },
  { key: 'other',   label: '📚 其他',        types: OTHER_TYPES },
];

function ItemsTab({ items, onOpenExchange }) {
  const [expandedId, setExpandedId] = useState(null);

  if (!items || items.length === 0) {
    return (
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:10, padding:'30px 0', color:'var(--text-dim)' }}>
        <div style={{ fontSize:32 }}>🎒</div>
        <div style={{ fontSize:12, textAlign:'center' }}>暂无能力或物品<br/>通过兑换系统获取</div>
        <button className="btn btn-gold btn-sm" onClick={onOpenExchange}>🛒 前往兑换</button>
      </div>
    );
  }

  const grouped = {};
  items.forEach(item => {
    let cat = 'other';
    if (ABILITY_TYPES.has(item.item_type))  cat = 'ability';
    else if (ITEM_TYPES_SET.has(item.item_type)) cat = 'item';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(item);
  });

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
      {CATEGORY_ORDER.map(({ key, label }) => {
        const group = grouped[key];
        if (!group || group.length === 0) return null;
        return (
          <div key={key}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-secondary)', letterSpacing:'0.05em',
              marginBottom:6, paddingBottom:4, borderBottom:'1px solid var(--border)' }}>
              {label} ({group.length})
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {group.map(item => {
                const isOpen = expandedId === item.id;
                const payload = typeof item.payload === 'string' ? JSON.parse(item.payload || '{}') : (item.payload || {});
                const desc = item.description || payload.desc || payload.description || '';
                const equipped = item.is_equipped;
                const canToggle = item.can_unequip;
                return (
                  <div key={item.id}
                    style={{
                      background: 'rgba(255,255,255,0.03)',
                      border: `1px solid ${isOpen ? 'var(--accent-blue)' : 'var(--border)'}`,
                      borderRadius: 8,
                      overflow:'hidden',
                      transition: 'border-color 0.2s',
                    }}>
                    {/* 收缩行 */}
                    <div
                      onClick={() => setExpandedId(isOpen ? null : item.id)}
                      style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', cursor:'pointer' }}>
                      <span style={{ fontSize:18, flexShrink:0 }}>{ITEM_ICONS[item.item_type] || '📦'}</span>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                          <span style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)',
                            whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>
                            {item.item_name || item.item_key}
                          </span>
                          {equipped ? (
                            <span style={{ fontSize:9, background:'rgba(79,156,249,0.2)', color:'var(--accent-blue)',
                              borderRadius:3, padding:'1px 4px', flexShrink:0 }}>已装备</span>
                          ) : (
                            <span style={{ fontSize:9, background:'rgba(255,255,255,0.05)', color:'var(--text-dim)',
                              borderRadius:3, padding:'1px 4px', flexShrink:0 }}>未装备</span>
                          )}
                        </div>
                        <div style={{ fontSize:10, color:'var(--text-dim)', marginTop:1 }}>
                          {ITEM_LABELS[item.item_type] || item.item_type}
                          {item.source_world ? ` · ${item.source_world}` : ''}
                        </div>
                      </div>
                      <div style={{ display:'flex', alignItems:'center', gap:6, flexShrink:0 }}>
                        <span style={{ fontSize:11, color:'var(--accent-gold)', fontWeight:700 }}>{item.final_tier ?? 0}★</span>
                        <span style={{ fontSize:10, color:'var(--text-dim)' }}>{isOpen ? '▲' : '▼'}</span>
                      </div>
                    </div>

                    {/* 展开详情 */}
                    {isOpen && (
                      <div style={{ padding:'0 10px 10px', borderTop:'1px solid var(--border)', paddingTop:8,
                        display:'flex', flexDirection:'column', gap:6 }}>
                        {desc && (
                          <div style={{ fontSize:12, color:'var(--text-secondary)', lineHeight:1.7,
                            background:'rgba(0,0,0,0.2)', borderRadius:6, padding:'6px 8px' }}>
                            {desc}
                          </div>
                        )}
                        {/* payload 额外字段渲染 */}
                        <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                          {payload.qty != null && (
                            <Tag label="数量" value={payload.qty} />
                          )}
                          {payload.aptitudeGrade && <Tag label="资质" value={payload.aptitudeGrade} color="var(--accent-blue)" />}
                          {payload.realm && <Tag label="当前境界" value={payload.realm} />}
                          {payload.poolMax != null && <Tag label="池上限" value={payload.poolMax} />}
                          {payload.poolRegen && <Tag label="回复" value={payload.poolRegen} />}
                          {payload.mastery && <Tag label="熟练度" value={payload.mastery} />}
                          {payload.type && <Tag label="类别" value={payload.type} />}
                        </div>
                        {canToggle ? (
                          <div style={{ fontSize:10, color:'var(--text-dim)' }}>可卸下 · 通过兑换系统管理</div>
                        ) : (
                          <div style={{ fontSize:10, color:'var(--text-dim)' }}>固有能力 · 无法卸除</div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Tag({ label, value, color }) {
  return (
    <div style={{ fontSize:10, background:'rgba(255,255,255,0.05)', borderRadius:4, padding:'2px 6px',
      color: color || 'var(--text-secondary)' }}>
      <span style={{ color:'var(--text-dim)' }}>{label}：</span>{value}
    </div>
  );
}

// ── 人际关系 Tab ─────────────────────────────────────────────────────────────
const EMOTION_CONFIG = {
  mixed:      { color: '#f59e0b', label: '混合', icon: '💫' },
  family:     { color: '#f97316', label: '亲情', icon: '❤️' },
  romance:    { color: '#ec4899', label: '爱情', icon: '💕' },
  friendship: { color: '#22c55e', label: '友情', icon: '🤝' },
  hostile:    { color: '#ef4444', label: '敌对', icon: '⚔️' },
  affiliated: { color: '#a78bfa', label: '从属', icon: '🔗' },
  knows:      { color: '#60a5fa', label: '认识', icon: '👋' },
  related:    { color: '#94a3b8', label: '相关', icon: '○'  },
};

function RelationsTab({ npcs, loading }) {
  const [expanded, setExpanded] = useState(null);

  if (loading) {
    return (
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', padding:40, color:'var(--text-dim)', gap:8 }}>
        <span className="spinner" /> 加载关系网络…
      </div>
    );
  }

  if (!npcs || npcs.length === 0) {
    return (
      <div style={{ textAlign:'center', color:'var(--text-dim)', padding:30, fontSize:13 }}>
        <div style={{ fontSize:28, marginBottom:8 }}>🔗</div>
        暂无已建立的人际关系<br />
        <span style={{ fontSize:11 }}>生成主角时背景中提到的人物会自动建档</span>
      </div>
    );
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ fontSize:11, color:'var(--text-dim)', padding:'4px 0 8px', borderBottom:'1px solid var(--border)', marginBottom:4 }}>
        共 {npcs.length} 位已知人物 · 点击展开详情
      </div>
      {npcs.map((npc, i) => {
        const ec = EMOTION_CONFIG[npc.emotion_type] || EMOTION_CONFIG.related;
        const affinity = npc.initial_affinity ?? 50;
        const isOpen = expanded === i;

        return (
          <div
            key={npc.name}
            style={{
              borderRadius: 6,
              border: `1px solid ${ec.color}33`,
              borderLeft: `3px solid ${ec.color}`,
              background: isOpen ? `${ec.color}08` : 'rgba(255,255,255,0.02)',
              overflow: 'hidden',
              transition: 'all 0.2s',
            }}
          >
            {/* 头部（点击展开/折叠） */}
            <div
              onClick={() => setExpanded(isOpen ? null : i)}
              style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', cursor:'pointer', userSelect:'none' }}
            >
              <span style={{ fontSize:14 }}>{ec.icon}</span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <span style={{ fontWeight:700, fontSize:13 }}>{npc.name}</span>
                  <span style={{ fontSize:10, background:`${ec.color}22`, color:ec.color, borderRadius:8, padding:'1px 6px' }}>
                    {ec.label}
                  </span>
                  {npc.npc_type === 'companion' && (
                    <span style={{ fontSize:10, color:'var(--accent-gold)' }}>★同伴</span>
                  )}
                </div>
                {/* 好感度条 */}
                <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:3 }}>
                  <div style={{ flex:1, height:3, borderRadius:2, background:'rgba(255,255,255,0.08)' }}>
                    <div style={{
                      height:'100%', borderRadius:2, background:ec.color,
                      width:`${affinity}%`, transition:'width 0.4s',
                    }} />
                  </div>
                  <span style={{ fontSize:10, color:ec.color, minWidth:22, textAlign:'right' }}>{affinity}</span>
                </div>
              </div>
              <span style={{ fontSize:10, color:'var(--text-dim)', transition:'transform 0.2s', transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}>›</span>
            </div>

            {/* 展开详情 */}
            {isOpen && (
              <div style={{ padding:'0 10px 10px', borderTop:`1px solid ${ec.color}22` }}>
                {npc.relation_label && (
                  <div style={{ fontSize:12, color:'var(--text-secondary)', margin:'8px 0 4px', fontStyle:'italic' }}>
                    「{npc.relation_label}」
                  </div>
                )}
                {npc.emotion_tags?.length > 0 && (
                  <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:6 }}>
                    {npc.emotion_tags.map((t, j) => (
                      <span key={j} style={{ fontSize:10, background:`${ec.color}18`, color:ec.color, borderRadius:8, padding:'1px 7px' }}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                {npc.background && (
                  <div style={{ fontSize:11, color:'var(--text-dim)', lineHeight:1.7, marginBottom:4 }}>
                    {npc.background}
                  </div>
                )}
                {npc.appearance && (
                  <div style={{ fontSize:11, color:'var(--text-secondary)', borderTop:`1px solid rgba(255,255,255,0.06)`, paddingTop:4, marginTop:4 }}>
                    <span style={{ color:'var(--text-dim)' }}>外貌：</span>{npc.appearance}
                  </div>
                )}
                {npc.loyalty_type && (
                  <div style={{ fontSize:10, color:'var(--text-dim)', marginTop:4 }}>
                    羁绊性质：{npc.loyalty_type}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
