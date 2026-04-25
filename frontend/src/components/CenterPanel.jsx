import { useEffect, useRef } from 'react';

const ITEM_TYPE_ICONS = {
  ApplicationTechnique: '⚡',
  PassiveAbility:       '🔮',
  PowerSource:          '💠',
  Bloodline:            '🩸',
  Mech:                 '🤖',
  Inventory:            '🎒',
  Companion:            '👥',
  Knowledge:            '📚',
  WorldTraverse:        '🌀',
};

export default function CenterPanel({ messages, isStreaming, novel }) {
  const bodyRef = useRef(null);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages]);

  const hasContent = messages.length > 0;

  return (
    <div className="glass-panel panel-center">
      {/* 顶部章节栏 */}
      <div className="novel-header">
        <div className="novel-chapter-label">
          {novel ? (
            <>📖 {novel.title || '未命名小说'} <span style={{ color: 'var(--text-dim)', marginLeft: 6 }}>零度叙事模式</span></>
          ) : '选择或创建小说'}
        </div>
        <div className="novel-actions">
          {novel && (
            <span className="badge badge-blue">
              {novel.world_type === 'multi_world' ? '多世界穿越' : '单一世界'}
            </span>
          )}
        </div>
      </div>

      {/* 正文区域 */}
      <div className="novel-body" ref={bodyRef}>
        {!hasContent && <WelcomeScreen />}
        {messages.map(msg => (
          <MessageBlock key={msg.id} msg={msg} />
        ))}
      </div>
    </div>
  );
}

function WelcomeScreen() {
  return (
    <div className="novel-welcome">
      <div className="novel-welcome-icon">📜</div>
      <div className="novel-welcome-title">零度叙事系统</div>
      <div className="novel-welcome-sub">
        选择一部小说并输入主角的行动，开始创作。<br />
        系统将通过 5 步工作流生成零度风格的叙事正文。
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
        {['零度写作', '物理细节', '世界推演', '四层记忆', '数值结算'].map(tag => (
          <span key={tag} className="badge badge-blue">{tag}</span>
        ))}
      </div>
    </div>
  );
}

function MessageBlock({ msg }) {
  if (msg.role === 'user') {
    return (
      <div style={{
        display: 'flex', justifyContent: 'flex-end',
        marginBottom: '1em',
        animation: 'fadeInUp 0.3s var(--ease-smooth)'
      }}>
        <div style={{
          maxWidth: '70%',
          background: 'rgba(79,156,249,0.12)',
          border: '1px solid rgba(79,156,249,0.25)',
          borderRadius: '12px 12px 4px 12px',
          padding: '10px 14px',
          fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6,
        }}>
          {msg.content}
        </div>
      </div>
    );
  }

  // assistant 消息 — 正文段落格式
  const paragraphs = (msg.content || '').split(/\n+/).filter(p => p.trim());

  return (
    <div style={{ marginBottom: '1.2em' }}>
      {paragraphs.map((para, i) => (
        <p
          key={i}
          className={`novel-paragraph ${para.startsWith('「') || para.startsWith('"') ? 'dialogue' : ''}`}
          style={{ animation: `fadeInUp ${0.2 + i * 0.05}s var(--ease-smooth)` }}
        >
          {para}
          {msg.streaming && i === paragraphs.length - 1 && (
            <span className="typing-cursor" />
          )}
        </p>
      ))}
    </div>
  );
}
