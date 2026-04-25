import { useState, useEffect } from 'react';
import { api } from '../api.js';

/**
 * RollbackModal — 显示最近可回滚的快照列表，执行单步撤回
 * Props:
 *   novelId       当前小说 ID
 *   onClose()     关闭弹窗
 *   onRollback()  回滚成功后的回调（用于刷新页面状态）
 */
export default function RollbackModal({ novelId, onClose, onRollback }) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [rolling, setRolling]     = useState(null); // snapshot_id being rolled back
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState('');

  useEffect(() => {
    loadSnapshots();
  }, [novelId]);

  const loadSnapshots = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getRollbackSnapshots(novelId, 5);
      setSnapshots(res.snapshots || []);
    } catch (e) {
      setError('加载快照失败：' + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async (snap) => {
    if (rolling) return;
    setRolling(snap.snapshot_id);
    setResult(null);
    setError('');
    try {
      const res = await api.rollbackToSnapshot(novelId, snap.snapshot_id);
      setResult(res);
      await onRollback(); // 刷新父组件状态
    } catch (e) {
      setError('回滚失败：' + e.message);
    } finally {
      setRolling(null);
    }
  };

  const formatTime = (iso) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return iso; }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        padding: '28px 28px 24px',
        width: 500,
        maxHeight: '80vh',
        overflowY: 'auto',
        boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
      }}>
        {/* 标题 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              ⏪ 回退到历史快照
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 3 }}>
              选择一条快照，系统将撤销该快照之后的所有回合
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--text-dim)', lineHeight: 1 }}
          >✕</button>
        </div>

        {/* 回滚成功提示 */}
        {result && (
          <div style={{
            background: 'rgba(52,211,153,0.1)', border: '1px solid rgba(52,211,153,0.3)',
            borderRadius: 8, padding: '12px 14px', marginBottom: 16, fontSize: 12,
            color: 'var(--accent-green)',
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>✓ 回滚成功</div>
            <div>{result.message}</div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
              已删除 {result.deleted_messages} 条消息
              {result.graph_removed > 0 && ` · 清理记忆节点 ${result.graph_removed} 个`}
              {result.medals_restored > 0 && ` · 凭证已恢复`}
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div style={{
            background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)',
            borderRadius: 8, padding: '10px 14px', marginBottom: 16,
            fontSize: 12, color: 'var(--accent-rose)',
          }}>
            ⚠ {error}
          </div>
        )}

        {/* 快照列表 */}
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
            <span className="spinner" style={{ width: 20, height: 20 }} />
          </div>
        ) : snapshots.length === 0 ? (
          <HardResetFallback novelId={novelId} rolling={rolling} setRolling={setRolling} setResult={setResult} setError={setError} onRollback={onRollback} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {snapshots.map((snap, idx) => (
              <SnapshotCard
                key={snap.snapshot_id}
                snap={snap}
                index={idx}
                formatTime={formatTime}
                rolling={rolling}
                onRollback={handleRollback}
              />
            ))}
          </div>
        )}

        {/* 底部说明 */}
        <div style={{
          marginTop: 20, paddingTop: 16,
          borderTop: '1px solid var(--border)',
          fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.7,
        }}>
          💡 回滚会恢复：主角状态 · 积分 · 凭证 · 成长记录 · 记忆图谱。<br />
          该快照之后的所有正文消息将被删除，此操作不可撤销。
        </div>
      </div>
    </div>
  );
}

function SnapshotCard({ snap, index, formatTime, rolling, onRollback }) {
  const isRolling = rolling === snap.snapshot_id;

  // messages_preview: [{role, preview}]
  const userMsg = snap.messages_preview?.find(m => m.role === 'user');
  const msgPreview = userMsg?.preview
    ? userMsg.preview.slice(0, 50) + (userMsg.preview.length > 50 ? '…' : '')
    : '（无用户输入）';

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '12px 14px',
      background: 'rgba(255,255,255,0.02)',
      transition: 'border-color 0.15s',
    }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* 序号 + 时间 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{
              fontSize: 9, fontWeight: 700, padding: '2px 6px',
              borderRadius: 4, background: 'rgba(79,156,249,0.15)',
              color: 'var(--accent-blue)',
            }}>
              {index === 0 ? '最新' : `−${index} 回合`}
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
              {formatTime(snap.created_at)}
            </span>
          </div>

          {/* 用户输入预览 */}
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 5 }}>
            {msgPreview}
          </div>

          {/* 快照时主角状态 */}
          <div style={{ display: 'flex', gap: 10, fontSize: 10, color: 'var(--text-dim)' }}>
            <span>👤 {snap.protagonist_name || '—'}</span>
            <span>💎 {snap.protagonist_points ?? '—'} 积分</span>
            <span>★ {snap.protagonist_tier ?? 0}M</span>
            <span>📩 第 {snap.user_message_order ?? '—'} 条前</span>
          </div>
        </div>

        {/* 回滚按钮 */}
        <button
          onClick={() => onRollback(snap)}
          disabled={!!rolling}
          style={{
            flexShrink: 0, marginLeft: 12,
            padding: '7px 14px',
            border: '1px solid rgba(244,63,94,0.4)',
            borderRadius: 7,
            background: 'rgba(244,63,94,0.08)',
            color: rolling ? 'var(--text-dim)' : 'var(--accent-rose)',
            fontSize: 11, fontWeight: 600, cursor: rolling ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', gap: 5,
            transition: 'all 0.15s',
          }}
        >
          {isRolling ? (
            <><span className="spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} /> 回滚中</>
          ) : (
            <>⏪ 回退到此</>
          )}
        </button>
      </div>
    </div>
  );
}

function HardResetFallback({ novelId, rolling, setRolling, setResult, setError, onRollback }) {
  const [confirm, setConfirm] = useState(false);
  const isResetting = rolling === '__hard_reset__';

  const handleReset = async () => {
    if (!confirm) { setConfirm(true); return; }
    setRolling('__hard_reset__');
    setResult(null);
    setError('');
    try {
      const res = await api.resetContent(novelId);
      setResult({
        message: res.message,
        deleted_messages: Object.values(res.deleted || {}).reduce((a, b) => a + b, 0),
        graph_removed: res.graph_nodes_removed || 0,
        medals_restored: 0,
      });
      setConfirm(false);
      await onRollback();
    } catch (e) {
      setError('重置失败：' + e.message);
    } finally {
      setRolling(null);
    }
  };

  return (
    <div style={{ textAlign: 'center', padding: '24px 0' }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
      <div style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 16 }}>
        暂无可回滚的快照<br />
        <span style={{ fontSize: 11 }}>每次回合结算后自动保存（最多保留 5 条）</span>
      </div>

      <div style={{
        border: '1px solid rgba(244,63,94,0.25)',
        borderRadius: 10, padding: '14px 16px',
        background: 'rgba(244,63,94,0.04)',
        textAlign: 'left',
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
          🗑 硬重置（清空全部正文）
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 12 }}>
          清空所有消息、积分、成长记录，恢复到刚初始化主角时的状态。<br />
          主角档案（姓名/性格/背景）和 NPC 档案将保留。
        </div>
        {confirm ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleReset}
              disabled={!!rolling}
              style={{
                flex: 1, padding: '8px', borderRadius: 7, border: 'none',
                background: 'rgba(244,63,94,0.8)', color: '#fff',
                fontSize: 12, fontWeight: 700, cursor: rolling ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              {isResetting
                ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} /> 重置中…</>
                : '⚠ 确认清空所有内容'}
            </button>
            <button
              onClick={() => setConfirm(false)}
              disabled={!!rolling}
              style={{
                padding: '8px 14px', borderRadius: 7,
                border: '1px solid var(--border)', background: 'none',
                color: 'var(--text-dim)', fontSize: 12, cursor: 'pointer',
              }}
            >
              取消
            </button>
          </div>
        ) : (
          <button
            onClick={handleReset}
            disabled={!!rolling}
            style={{
              width: '100%', padding: '8px', borderRadius: 7,
              border: '1px solid rgba(244,63,94,0.4)',
              background: 'rgba(244,63,94,0.08)',
              color: 'var(--accent-rose)', fontSize: 12, fontWeight: 600,
              cursor: rolling ? 'not-allowed' : 'pointer',
            }}
          >
            🗑 执行硬重置
          </button>
        )}
      </div>
    </div>
  );
}
