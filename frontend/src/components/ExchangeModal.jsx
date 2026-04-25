import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api.js';

export default function ExchangeModal({ novelId, onClose, onPurchased }) {
  const [view, setView]         = useState('catalog');
  const [items, setItems]       = useState([]);
  const [filteredItems, setFilteredItems] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [evalResult, setEval]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const [customName, setName]   = useState('');
  const [customWorld, setWorld] = useState('');
  const [customLore, setLore]   = useState('');
  const [customDesc, setDesc]   = useState('');
  const [customType, setType]   = useState('PassiveAbility');  // Fix #12

  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimerRef = useRef(null);

  useEffect(() => {
    loadCatalog();
  }, [novelId]);

  // 服务端防抖搜索（300ms），空查询时恢复全量目录
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (!searchQuery.trim()) {
      setFilteredItems(items);
      return;
    }
    searchTimerRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await api.searchExchange(novelId, {
          query: searchQuery,
          item_type: '',
          protagonist_tier: 0,
        });
        setFilteredItems(res.results || res.items || []);
      } catch {
        // 服务端搜索失败时降级本地过滤
        const q = searchQuery.toLowerCase();
        setFilteredItems(items.filter(item =>
          (item.item_name || '').toLowerCase().includes(q) ||
          (item.source_world || '').toLowerCase().includes(q) ||
          (item.item_type || '').toLowerCase().includes(q)
        ));
      } finally { setSearchLoading(false); }
    }, 300);
    return () => clearTimeout(searchTimerRef.current);
  }, [searchQuery, items, novelId]);

  const loadCatalog = async (refresh = false) => {
    setLoading(true);
    try {
      const { items: list } = await api.getCatalog(novelId, refresh);
      setItems(list || []);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  const handleEvaluate = async (item) => {
    setSelected(item);
    setError('');

    // 如果目录已包含精确评估结果，直接跳过 LLM——无需二次调用
    if (item.eval_result) {
      setEval(item.eval_result);
      setView('result');
      return;
    }

    // 降级路径：缓存中无评估结果，走传统三轮评估
    setView('evaluate');
    setLoading(true);
    try {
      const res = await api.evaluateItem(novelId, {
        item_name:        item.item_name || item.item_key,
        source_world:     item.source_world || '',
        lore_context:     item.lore_context || '',
        item_description: item.description || '',
      });
      setEval(res);
      setView('result');
    } catch (e) {
      setError(e.message);
      setView('catalog');
    } finally { setLoading(false); }
  };

  const handleCustomEvaluate = async () => {
    if (!customName.trim()) { setError('请输入物品名称'); return; }
    setLoading(true); setError('');
    const item = { item_name: customName, source_world: customWorld, item_key: customName.toLowerCase().replace(/\s+/g,'_'), item_type: customType };
    setSelected(item);
    setView('evaluate');
    try {
      const res = await api.evaluateItem(novelId, {
        item_name: customName, source_world: customWorld,
        lore_context: customLore, item_description: customDesc,
        item_type: customType,
      });
      setEval(res);
      setView('result');
    } catch (e) {
      setError(e.message); setView('custom');
    } finally { setLoading(false); }
  };

  const handlePurchase = async () => {
    if (!evalResult) return;
    setLoading(true); setError('');
    try {
      const res = await api.purchaseItem(novelId, {
        item_key:     selected?.item_key || evalResult.item_name?.toLowerCase().replace(/\s+/g,'_'),
        item_name:    evalResult.item_name,
        item_type:    selected?.item_type || 'ApplicationTechnique',
        source_world: evalResult.source_world || '',
        final_price:  evalResult.final_price,
        final_tier:   evalResult.final_tier,
        final_sub:    evalResult.final_sub || 'M',  // FE-4: fallback
        payload:      selected?.payload || {},
      });
      await onPurchased?.(res);   // FE-5: 先刷新积分再关闭
      onClose();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel modal-box exchange-modal">
        {/* 顶部导航 */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:18 }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <h2 style={{ fontFamily:'var(--font-title)', fontSize:18, color:'var(--accent-gold)' }}>
              🛒 跨次元兑换商
            </h2>
            {view !== 'catalog' && (
              <button className="btn btn-ghost btn-sm" onClick={() => { setView('catalog'); setError(''); }}>
                ← 返回目录
              </button>
            )}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {error && (
          <div style={{ background:'rgba(249,123,114,0.08)', border:'1px solid rgba(249,123,114,0.25)', borderRadius:'var(--radius-sm)', padding:'10px 14px', marginBottom:14, color:'var(--accent-rose)', fontSize:13 }}>
            ⚠️ {error}
          </div>
        )}

        {/* ── 目录视图 ── */}
        {view === 'catalog' && (
          <>
            <div style={{ display:'flex', gap:8, marginBottom:14 }}>
              <button className="btn btn-ghost" onClick={() => loadCatalog(true)} disabled={loading}>
                {loading ? <span className="spinner" /> : '🔄'} 刷新目录
              </button>
              <button className="btn btn-ghost" onClick={() => setView('custom')}>
                ✏️ 自定义评估
              </button>
              <div style={{ flex:1, position:'relative', minWidth:0 }}>
                <input
                  className="input-field"
                  style={{ width:'100%', fontSize:12, padding:'4px 32px 4px 10px', height:32, boxSizing:'border-box' }}
                  placeholder="🔍 搜索物品名/来源宇宙/类型…"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />
                {searchLoading && (
                  <span className="spinner" style={{ position:'absolute', right:8, top:'50%', transform:'translateY(-50%)', width:12, height:12, borderWidth:1.5 }} />
                )}
              </div>
            </div>

            {loading && items.length === 0 ? (
              <div style={{ textAlign:'center', padding:'30px 0', color:'var(--text-dim)' }}>
                <div className="spinner" style={{ margin:'0 auto 10px' }} />
                <div>生成兑换目录中…</div>
                <div style={{ fontSize:11, marginTop:6, color:'var(--text-dim)', lineHeight:1.6 }}>
                  Step 1：LLM 生成目录列表<br />
                  Step 2：并发三轮评估协议，获取精确价格（稍等）
                </div>
              </div>
            ) : (
              <div className="catalog-grid">
                {filteredItems.map((item, i) => (
                  <CatalogCard key={item.item_key || i} item={item} onEvaluate={handleEvaluate} />
                ))}
                {filteredItems.length === 0 && !loading && (
                  <div style={{ gridColumn:'1/-1', textAlign:'center', color:'var(--text-dim)', padding:'30px 0', fontSize:13 }}>
                    {searchQuery ? `没有匹配「${searchQuery}」的物品` : '目录为空，点击「刷新目录」生成当前世界的可兑换物品'}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* ── 评估等待 ── */}
        {view === 'evaluate' && (
          <div style={{ textAlign:'center', padding:'40px 0', color:'var(--text-secondary)' }}>
            <div className="spinner" style={{ width:32, height:32, borderWidth:3, margin:'0 auto 16px' }} />
            <div style={{ fontSize:15, marginBottom:8 }}>三轮评估协议进行中…</div>
            <div style={{ fontSize:12, color:'var(--text-dim)' }}>
              正在评估：{selected?.item_name || selected?.item_key}<br />
              Round 1A → 属性提纯 → Round 1D → 修正项 → 最终星级
            </div>
          </div>
        )}

        {/* ── 评估结果 ── */}
        {view === 'result' && evalResult && (
          <EvalResult result={evalResult} loading={loading} error={error} onPurchase={handlePurchase} />
        )}

        {view === 'custom' && (
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <div style={{ fontSize:12, color:'var(--text-secondary)', marginBottom:4 }}>
              输入任意角色/技能信息，获得三轮评估报告和兑换价格
            </div>
            <div>
              <label style={{ fontSize:11, color:'var(--text-secondary)', display:'block', marginBottom:3 }}>物品/角色名称 *</label>
              <input className="input-field" placeholder="e.g. 七夜神君·血魔" value={customName} onChange={e => setName(e.target.value)} />
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              <div>
                <label style={{ fontSize:11, color:'var(--text-secondary)', display:'block', marginBottom:3 }}>物品类型</label>
                <select className="input-field" style={{ fontSize:12 }} value={customType} onChange={e => setType(e.target.value)}>
                  <option value="PassiveAbility">被动能力</option>
                  <option value="ApplicationTechnique">应用技巧</option>
                  <option value="PowerSource">能量基盘</option>
                  <option value="Bloodline">血统体质</option>
                  <option value="Inventory">物品装备</option>
                  <option value="Knowledge">知识理论</option>
                  <option value="WorldTraverse">世界坐标</option>
                  <option value="Companion">同伴</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize:11, color:'var(--text-secondary)', display:'block', marginBottom:3 }}>来源宇宙</label>
                <input className="input-field" style={{ fontSize:12 }} placeholder="e.g. Fate/stay night" value={customWorld} onChange={e => setWorld(e.target.value)} />
              </div>
            </div>
            <div>
              <label style={{ fontSize:11, color:'var(--text-secondary)', display:'block', marginBottom:3 }}>原著壮举参考</label>
              <textarea className="input-field" style={{ minHeight:80, resize:'vertical' }} placeholder="描述该角色/技能的关键表现…" value={customLore} onChange={e => setLore(e.target.value)} />
            </div>
            <div>
              <label style={{ fontSize:11, color:'var(--text-secondary)', display:'block', marginBottom:3 }}>技能效果描述</label>
              <textarea className="input-field" style={{ minHeight:60, resize:'vertical' }} placeholder="技能机制、使用条件、持续时间…" value={customDesc} onChange={e => setDesc(e.target.value)} />
            </div>
            <button className="btn btn-gold btn-lg" onClick={handleCustomEvaluate} disabled={loading}>
              {loading ? <><span className="spinner" /> 评估中…</> : '🔍 开始三轮评估'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CatalogCard({ item, onEvaluate }) {
  const TYPE_ICONS = {
    ApplicationTechnique:'⚡', PassiveAbility:'🔮', PowerSource:'💠',
    Bloodline:'🩸', Inventory:'🎒', Companion:'👥', Knowledge:'📚', WorldTraverse:'🌀', Mech:'🤖',
  };
  const TYPE_LABELS = {
    ApplicationTechnique:'应用技巧', PassiveAbility:'被动能力', PowerSource:'力量基盘',
    Bloodline:'血统体质', Inventory:'物品装备', Companion:'同伴', Knowledge:'知识理论', WorldTraverse:'世界坐标', Mech:'机甲',
  };
  const isLocked   = item.locked;
  const isLimited  = item.is_limited;
  const isPrecious = item.is_precious;
  const isPrecise  = !!item.eval_result;  // 已经过三轮精确评估

  // 优先使用三轮评估结果中的精确星级和价格
  const displayTier  = item.final_tier  ?? item.base_tier;
  const displaySub   = item.final_sub   ?? item.base_tier_sub ?? 'M';
  const displayPrice = item.final_price ?? item.estimated_price ?? 0;

  return (
    <div
      className="catalog-item"
      onClick={() => !isLocked && onEvaluate(item)}
      title={isLocked ? `🔒 需要 ${displayTier}★ 凭证方可兑换` : isPrecise ? '点击查看精确评估结果' : '点击进行三轮评估'}
      style={{ opacity: isLocked ? 0.55 : 1, cursor: isLocked ? 'not-allowed' : 'pointer',
               border: isLimited ? '1px solid rgba(249,123,114,0.4)' : undefined }}
    >
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontSize:20 }}>{TYPE_ICONS[item.item_type] || '📦'}</span>
        <div style={{ flex:1, minWidth:0 }}>
          <div className="catalog-item-name">{item.item_name}</div>
          <div className="catalog-item-world">{item.source_world || '本源'}</div>
        </div>
        <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:2, flexShrink:0 }}>
          {isLocked   && <span style={{ fontSize:10, color:'var(--accent-rose)' }}>🔒 锁定</span>}
          {isLimited  && <span style={{ fontSize:10, color:'var(--accent-rose)' }}>⏰ 限定</span>}
          {isPrecious && <span style={{ fontSize:10, color:'var(--accent-gold)' }}>💎 珍贵</span>}
          {item.is_gd && <span style={{ fontSize:10, color:'var(--accent-emerald)' }}>🌱 GD</span>}
        </div>
      </div>
      <div style={{ fontSize:11, color:'var(--text-secondary)', lineHeight:1.4 }}>
        {item.description?.slice(0, 60)}{item.description?.length > 60 ? '…' : ''}
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <span className="badge badge-blue">{TYPE_LABELS[item.item_type] || item.item_type}</span>
        <span className="catalog-item-price" style={{ display:'flex', alignItems:'center', gap:4 }}>
          {isPrecise && (
            <span title="三轮评估精确价格" style={{
              fontSize:9, color:'var(--accent-emerald)',
              border:'1px solid var(--accent-emerald)', borderRadius:3,
              padding:'1px 3px', lineHeight:1.4,
            }}>✓精确</span>
          )}
          {displayTier}★{displaySub} · {displayPrice.toLocaleString()}分
        </span>
      </div>
    </div>
  );
}

function EvalResult({ result, loading, error, onPurchase }) {
  const tierLabel = `${result.final_tier}★${result.final_sub}`;
  const modifiers = result.modifiers || {};

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
      {/* 结果头部 */}
      <div style={{
        padding:'16px', borderRadius:'var(--radius-md)',
        background:'rgba(245,200,66,0.08)', border:'1px solid var(--border-gold)',
        display:'flex', justifyContent:'space-between', alignItems:'center',
      }}>
        <div>
          <div style={{ fontFamily:'var(--font-title)', fontSize:17, color:'var(--accent-gold)', marginBottom:4 }}>
            {result.item_name}
          </div>
          <div style={{ fontSize:12, color:'var(--text-secondary)' }}>来源：{result.source_world || '未知'}</div>
        </div>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:28, fontWeight:700, color:'var(--accent-gold)' }}>
            {tierLabel}
          </div>
          <div style={{ fontFamily:'var(--font-mono)', fontSize:16, color:'var(--text-primary)', marginTop:2 }}>
            {(result.final_price || 0).toLocaleString()} 积分
          </div>
        </div>
      </div>

      {/* 评估详情 */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {[
          ['第一轮临时星级', `${result.temp_tier}★${result.temp_sub}`],
          ['覆盖维度', `${result.covered_dims ?? 0} / 10`],
          ['基准积分', (result.base_price || 0).toLocaleString()],
          ['最终积分', (result.final_price || 0).toLocaleString()],
        ].map(([label, val]) => (
          <div key={label} style={{
            padding:'8px 12px', borderRadius:'var(--radius-sm)',
            background:'rgba(255,255,255,0.03)', border:'1px solid var(--border)',
          }}>
            <div style={{ fontSize:10, color:'var(--text-secondary)', marginBottom:3 }}>{label}</div>
            <div style={{ fontFamily:'var(--font-mono)', fontSize:14, fontWeight:600, color:'var(--text-primary)' }}>{val}</div>
          </div>
        ))}
      </div>

      {/* 修正项摘要 */}
      {modifiers.eval_notes && (
        <div style={{
          padding:'10px 14px', borderRadius:'var(--radius-sm)',
          background:'rgba(79,156,249,0.06)', border:'1px solid var(--border)',
          fontSize:12, color:'var(--text-secondary)', lineHeight:1.6,
        }}>
          📋 {modifiers.eval_notes}
        </div>
      )}

      {/* Hax提示 */}
      {modifiers.hax_hi > 0 && (
        <div className="badge badge-purple" style={{ alignSelf:'flex-start' }}>
          ✨ Hax等级 HI-{modifiers.hax_hi}
        </div>
      )}

      {error && (
        <div style={{ color:'var(--accent-rose)', fontSize:12 }}>⚠️ {error}</div>
      )}

      <button
        className="btn btn-gold btn-lg"
        style={{ width:'100%', marginTop:4 }}
        onClick={onPurchase}
        disabled={loading}
      >
        {loading ? <><span className="spinner" /> 兑换中…</> : `🛒 确认兑换 · ${(result.final_price || 0).toLocaleString()} 积分`}
      </button>
    </div>
  );
}
