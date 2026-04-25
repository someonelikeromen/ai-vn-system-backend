/**
 * ProtagonistGeneratorModal.jsx
 * AI 主角生成向导 — 三模式：
 *   quick      — 快速生成（仅填偏好关键词）
 *   background — 背景描述生成
 *   quiz       — 人格问卷生成（LLM 出题 → 用户作答 → LLM 生成）
 */
import { useState, useEffect, useRef } from 'react';
import { api } from '../api.js';

// ── 穿越方式选项 ──────────────────────────────────────────────────────────────
const TRAVERSAL_METHODS = [
  { id: 'isekai',     label: '异世界转生', desc: '死后重生，保有完整记忆，可能附带转生祝福' },
  { id: 'rebirth',    label: '重生',       desc: '以完整记忆在本世界更早时间点重新出生' },
  { id: 'possession', label: '夺舍/融合',  desc: '穿入已存在人物身体，继承部分原主记忆' },
  { id: 'summoning',  label: '召唤/降临',  desc: '以原世界成年身份被召唤至本世界' },
  { id: 'system',     label: '系统穿越',   desc: '携带系统界面降临，可能附带新手礼包' },
  { id: 'custom',     label: '自定义',     desc: '自行描述穿越方式' },
];

// ── 快速生成的风格模板 ────────────────────────────────────────────────────────
const QUICK_TEMPLATES = [
  { label: '普通人',     icon: '🧑', text: '普通现代城市人，有点拖延，在人际关系中有些被动' },
  { label: '学者型',     icon: '📚', text: '爱读书的理科生，社交圈窄，遇到新知识会停不下来' },
  { label: '军事化',     icon: '⚔️', text: '有过军事或格斗训练背景，习惯规则，但内心有某些执念' },
  { label: '社会边缘',   icon: '🌑', text: '游走在社会边缘，有过一段挣扎的经历，某件事让他重新站起来' },
  { label: '艺术气质',   icon: '🎨', text: '有艺术敏感性，容易被细节触动，情绪起伏大，有时候很自我' },
  { label: '随机惊喜',   icon: '🎲', text: '' },  // 空 = AI 完全自由发挥
];

export default function ProtagonistGeneratorModal({ novelId, initialWorldKey, onClose, onGenerated }) {
  // ── 总流程状态 ─────────────────────────────────────────────────
  const [phase, setPhase] = useState('mode');   // mode | config | quiz | generating | preview
  const [mode, setMode]   = useState('');        // quick | background | quiz

  // ── 共用偏好 ──────────────────────────────────────────────────
  const [charType,        setCharType]        = useState('本土');
  const [traversalMethod, setTraversalMethod] = useState('isekai');
  const [traversalDesc,   setTraversalDesc]   = useState('');
  const [nameHint,        setNameHint]        = useState('');
  const [genderHint,      setGenderHint]      = useState('');
  const [ageHint,         setAgeHint]         = useState('');
  const [startPts,        setStartPts]        = useState(0);

  // ── quick 模式 ────────────────────────────────────────────────
  const [quickTemplate, setQuickTemplate] = useState('');
  const [quickExtra,    setQuickExtra]    = useState('');

  // ── background 模式 ────────────────────────────────────────────
  const [background, setBackground] = useState('');

  // ── quiz 模式 ─────────────────────────────────────────────────
  const [questions,    setQuestions]    = useState([]);
  const [answers,      setAnswers]      = useState({});   // id → answer string
  const [qLoading,     setQLoading]     = useState(false);
  const [qError,       setQError]       = useState('');
  const [currentQIdx,  setCurrentQIdx]  = useState(0);

  // ── result ────────────────────────────────────────────────────
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState('');
  const [result,     setResult]     = useState(null);
  const [error,      setError]      = useState('');

  const progressTimerRef = useRef(null);

  // ── 选择模式后跳到 config 配置 ───────────────────────────────
  const handleSelectMode = (m) => {
    setMode(m);
    setPhase('config');
  };

  // ── 开始 quiz：生成题目 ──────────────────────────────────────
  const handleStartQuiz = async () => {
    setQLoading(true); setQError('');
    try {
      const { questions: qs } = await api.getGenerationQuestions(novelId, charType, 10);
      setQuestions(qs || []);
      setCurrentQIdx(0);
      setPhase('quiz');
    } catch (e) {
      setQError('生成题目失败：' + e.message);
    } finally {
      setQLoading(false);
    }
  };

  // ── 生成进度动画 ──────────────────────────────────────────────
  const startProgressAnim = () => {
    const msgs = [
      '正在分析性格维度…', '构建背景故事…', '推导心理触发模式…',
      '计算属性面板…', '分配知识图谱…', '检查反理性化铁律…',
      '生成完整档案…', '即将完成…',
    ];
    let i = 0;
    setGenProgress(msgs[0]);
    progressTimerRef.current = setInterval(() => {
      i = Math.min(i + 1, msgs.length - 1);
      setGenProgress(msgs[i]);
    }, 2200);
  };

  const stopProgressAnim = () => {
    clearInterval(progressTimerRef.current);
  };

  // ── 提交生成 ─────────────────────────────────────────────────
  const handleGenerate = async (commitNow = false) => {
    setGenerating(true); setError(''); setPhase('generating');
    startProgressAnim();

    const body = {
      mode,
      commit: commitNow,
      char_type: charType,
      traversal_method: charType === '穿越者' ? traversalMethod : '',
      traversal_desc:   charType === '穿越者' && traversalMethod === 'custom' ? traversalDesc : '',
      name_hint:    nameHint,
      gender_hint:  genderHint,
      age_hint:     ageHint,
      starting_points: startPts,
      world_key: initialWorldKey || '',
    };

    if (mode === 'quick') {
      body.background = quickTemplate === '' ? quickExtra :
        (quickTemplate + (quickExtra ? '；' + quickExtra : ''));
    } else if (mode === 'background') {
      body.background = background;
    } else if (mode === 'quiz') {
      body.quiz_answers = questions.map((q, i) => ({
        question: q.question,
        answer:   answers[q.id ?? i] || '',
      }));
    }

    try {
      const res = await api.generateProtagonist(novelId, body);
      stopProgressAnim();
      res._reqBody = body;
      setResult(res);
      setPhase('preview');
    } catch (e) {
      stopProgressAnim();
      setError(e.message);
      setPhase(mode === 'quiz' ? 'quiz' : 'config');
    } finally {
      setGenerating(false);
    }
  };

  // ── 确认写入 ─────────────────────────────────────────────────
  const handleCommit = async () => {
    if (result?.committed) {
      // 已写入，直接回调
      onGenerated?.(result);
      onClose();
      return;
    }
    // 如果是预览模式，再次调用 commit=true
    setGenerating(true); setError('');
    try {
      const body = { ...result._reqBody, commit: true, direct_character_data: result.character };
      const res = await api.generateProtagonist(novelId, body);
      // 合并 generated_npcs
      const finalRes = { ...res, generated_npcs: res.generated_npcs || [] };
      setResult(prev => ({ ...prev, ...finalRes, committed: true }));
      onGenerated?.(finalRes);
    } catch (e) {
      setError(e.message);
      setGenerating(false);
    }
  };

  // ──────────────────────────────────────────────────────────────
  // 渲染
  // ──────────────────────────────────────────────────────────────

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box gen-modal">

        {/* Header */}
        <div className="modal-header">
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            {phase !== 'mode' && (
              <button className="btn btn-ghost btn-sm" style={{ padding:'4px 8px' }}
                onClick={() => {
                  if (phase === 'quiz') setPhase('config');
                  else if (phase === 'preview') setPhase(mode === 'quiz' ? 'quiz' : 'config');
                  else setPhase('mode');
                }}
              >←</button>
            )}
            <div>
              <div className="modal-title">✨ AI 主角生成向导</div>
              <div style={{ fontSize:11, color:'var(--text-dim)', marginTop:2 }}>
                { phase === 'mode'       ? '选择生成方式'
                : phase === 'config'    ? '基础配置'
                : phase === 'quiz'      ? `第 ${currentQIdx+1} / ${questions.length} 题`
                : phase === 'generating'? genProgress
                : '预览 & 确认' }
              </div>
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {/* ── Phase: mode 选择 ── */}
        {phase === 'mode' && <ModeSelect onSelect={handleSelectMode} />}

        {/* ── Phase: config 基础配置 ── */}
        {phase === 'config' && (
          <ConfigPhase
            mode={mode}
            // quick props
            quickTemplate={quickTemplate} setQuickTemplate={setQuickTemplate}
            quickExtra={quickExtra}       setQuickExtra={setQuickExtra}
            // background props
            background={background} setBackground={setBackground}
            // 共用
            charType={charType}               setCharType={setCharType}
            traversalMethod={traversalMethod} setTraversalMethod={setTraversalMethod}
            traversalDesc={traversalDesc}     setTraversalDesc={setTraversalDesc}
            nameHint={nameHint}   setNameHint={setNameHint}
            genderHint={genderHint} setGenderHint={setGenderHint}
            ageHint={ageHint}     setAgeHint={setAgeHint}
            startPts={startPts}   setStartPts={setStartPts}
            // actions
            qLoading={qLoading}   qError={qError}
            onStartQuiz={handleStartQuiz}
            onGenerate={() => handleGenerate(false)}
          />
        )}

        {/* ── Phase: quiz 答题 ── */}
        {phase === 'quiz' && (
          <QuizPhase
            questions={questions}
            answers={answers}  setAnswers={setAnswers}
            currentIdx={currentQIdx} setCurrentIdx={setCurrentQIdx}
            onGenerate={() => handleGenerate(false)}
            error={error}
          />
        )}

        {/* ── Phase: generating ── */}
        {phase === 'generating' && <GeneratingPhase progress={genProgress} />}

        {/* ── Phase: preview ── */}
        {phase === 'preview' && result && (
          <PreviewPhase
            character={result.character}
            committed={result.committed}
            generatedNpcs={result.generated_npcs || []}
            onChange={(newChar) => setResult({...result, character: newChar})}
            error={error}
            generating={generating}
            onBack={() => setPhase(mode === 'quiz' ? 'quiz' : 'config')}
            onRegenerate={() => handleGenerate(false)}
            onCommit={handleCommit}
            onDone={() => { onGenerated?.(result); onClose(); }}
          />
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Phase Components
══════════════════════════════════════════════════════════════════════════ */

// ── 选择模式 ──────────────────────────────────────────────────────────────────
function ModeSelect({ onSelect }) {
  const modes = [
    {
      id: 'quick',
      icon: '⚡',
      label: '快速生成',
      desc: '选择性格模板 + 几个关键词，30秒出角色',
      color: 'var(--accent-green)',
    },
    {
      id: 'background',
      icon: '📝',
      label: '背景描述',
      desc: '写下你对主角的设定，AI 据此推断深层性格',
      color: 'var(--accent-blue)',
    },
    {
      id: 'quiz',
      icon: '🧩',
      label: '人格问卷',
      desc: 'AI 出10道情境测试题，根据你的回答生成最真实的主角',
      color: 'var(--accent-purple)',
    },
  ];
  return (
    <div className="gen-phase-body">
      <div className="gen-mode-tip">选择你想要的角色生成方式</div>
      <div className="gen-mode-grid">
        {modes.map(m => (
          <button key={m.id} className="gen-mode-card" style={{ '--mcolor': m.color }}
            onClick={() => onSelect(m.id)}
          >
            <span className="gen-mode-icon">{m.icon}</span>
            <span className="gen-mode-label">{m.label}</span>
            <span className="gen-mode-desc">{m.desc}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 基础配置 ──────────────────────────────────────────────────────────────────
function ConfigPhase({
  mode, quickTemplate, setQuickTemplate, quickExtra, setQuickExtra,
  background, setBackground,
  charType, setCharType, traversalMethod, setTraversalMethod,
  traversalDesc, setTraversalDesc,
  nameHint, setNameHint, genderHint, setGenderHint,
  ageHint, setAgeHint, startPts, setStartPts,
  qLoading, qError, onStartQuiz, onGenerate,
}) {
  const isQuiz = mode === 'quiz';

  return (
    <div className="gen-phase-body">

      {/* MODE SPECIFIC */}
      {mode === 'quick' && (
        <section className="gen-section">
          <div className="gen-section-title">⚡ 性格模板</div>
          <div className="gen-template-grid">
            {QUICK_TEMPLATES.map(t => (
              <button
                key={t.label}
                className={`gen-template-btn ${quickTemplate === t.text ? 'selected' : ''}`}
                onClick={() => setQuickTemplate(t.text)}
              >
                <span>{t.icon}</span>
                <span>{t.label}</span>
              </button>
            ))}
          </div>
          <div className="gen-field" style={{ marginTop:12 }}>
            <label>补充关键词（可选）</label>
            <input className="settings-input"
              placeholder="e.g. 怕黑、双重性格、前警察…"
              value={quickExtra}
              onChange={e => setQuickExtra(e.target.value)}
            />
          </div>
        </section>
      )}

      {mode === 'background' && (
        <section className="gen-section">
          <div className="gen-section-title">📝 人物背景 / 设定</div>
          <div className="gen-field">
            <label>描述你想要的主角（越具体越好）</label>
            <textarea
              className="settings-input"
              style={{ minHeight:160, resize:'vertical', lineHeight:1.8 }}
              placeholder={`示例：\n一个在小城市长大的前消防员，25岁，因为一次救援事故失去了工作伙伴，心里总觉得是自己的责任。现在在城里跑外卖，平时话不多，但遇到熟人会有点话痨。有轻微的强迫症，睡前一定要把东西摆整齐…`}
              value={background}
              onChange={e => setBackground(e.target.value)}
            />
            <div style={{ fontSize:11, color:'var(--text-dim)', marginTop:4 }}>
              💡 AI 会根据你的描述推断深层性格，不会照搬原文。有矛盾、有缺陷的描述效果最好。
            </div>
          </div>
        </section>
      )}

      {mode === 'quiz' && (
        <section className="gen-section">
          <div className="gen-section-title">🧩 人格问卷模式</div>
          <div className="gen-quiz-intro">
            <p>AI 将生成 <strong>10 道情境测试题</strong>，每道题都设计来揭示你「不愿承认的真实倾向」。</p>
            <p>你的回答会被用来推断主角的深层性格——<strong>不要过度思考，选直觉反应</strong>。</p>
          </div>
          {qError && <div className="gen-error">{qError}</div>}
        </section>
      )}

      {/* 角色类型 */}
      <section className="gen-section">
        <div className="gen-section-title">🌍 角色类型</div>
        <div className="gen-type-row">
          {['本土', '穿越者'].map(t => (
            <button
              key={t}
              className={`gen-type-btn ${charType === t ? 'selected' : ''}`}
              onClick={() => setCharType(t)}
            >
              {t === '本土' ? '🏡 本土原住民' : '🌀 穿越者'}
            </button>
          ))}
        </div>

        {charType === '穿越者' && (
          <div style={{ marginTop:12 }}>
            <div className="gen-field">
              <label>穿越方式</label>
              <div className="gen-traversal-grid">
                {TRAVERSAL_METHODS.map(m => (
                  <button
                    key={m.id}
                    className={`gen-traversal-btn ${traversalMethod === m.id ? 'selected' : ''}`}
                    onClick={() => setTraversalMethod(m.id)}
                    title={m.desc}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            {traversalMethod === 'custom' && (
              <div className="gen-field" style={{ marginTop:8 }}>
                <label>自定义穿越方式描述</label>
                <textarea className="settings-input" style={{ minHeight:60 }}
                  placeholder="描述穿越的具体方式和条件…"
                  value={traversalDesc}
                  onChange={e => setTraversalDesc(e.target.value)}
                />
              </div>
            )}
          </div>
        )}
      </section>

      {/* 可选偏好 */}
      <section className="gen-section">
        <div className="gen-section-title" style={{ cursor:'pointer' }}>
          🔧 可选偏好（留空 AI 自由决定）
        </div>
        <div className="gen-prefs-grid">
          <div className="gen-field">
            <label>姓名提示</label>
            <input className="settings-input" placeholder="e.g. 吴森 / 希望有中文名"
              value={nameHint} onChange={e => setNameHint(e.target.value)} />
          </div>
          <div className="gen-field">
            <label>性别</label>
            <select className="settings-select"
              value={genderHint} onChange={e => setGenderHint(e.target.value)}>
              <option value="">AI 自定</option>
              <option value="男">男</option>
              <option value="女">女</option>
              <option value="不限">不限</option>
            </select>
          </div>
          <div className="gen-field">
            <label>年龄范围</label>
            <input className="settings-input" placeholder="e.g. 20-25岁"
              value={ageHint} onChange={e => setAgeHint(e.target.value)} />
          </div>
          <div className="gen-field">
            <label>初始积分</label>
            <input className="settings-input" type="number" min="0" placeholder="0"
              value={startPts || ''} onChange={e => setStartPts(parseInt(e.target.value) || 0)} />
          </div>
        </div>
      </section>

      {/* Actions */}
      <div className="gen-actions">
        {isQuiz ? (
          <button className="btn btn-primary" style={{ flex:1 }}
            onClick={onStartQuiz} disabled={qLoading}>
            {qLoading ? <><span className="spinner" /> 生成题目中…</> : '🧩 开始问卷'}
          </button>
        ) : (
          <button className="btn btn-primary" style={{ flex:1 }}
            onClick={onGenerate}
            disabled={mode === 'background' && !background.trim()}>
            ✨ 生成主角
          </button>
        )}
      </div>
    </div>
  );
}

// ── 答题 ──────────────────────────────────────────────────────────────────────
function QuizPhase({ questions, answers, setAnswers, currentIdx, setCurrentIdx, onGenerate, error }) {
  if (!questions.length) return <div style={{ padding:24, color:'var(--text-dim)' }}>加载中…</div>;

  const q = questions[currentIdx];
  const qId = q.id ?? currentIdx;
  const answered = answers[qId];
  const total = questions.length;
  const isLast = currentIdx === total - 1;
  const answeredCount = Object.keys(answers).length;

  const setAns = (val) => setAnswers(prev => ({ ...prev, [qId]: val }));

  return (
    <div className="gen-phase-body">
      {/* 进度条 */}
      <div className="gen-quiz-progress">
        <div className="gen-quiz-bar">
          <div className="gen-quiz-fill" style={{ width: `${(answeredCount / total) * 100}%` }} />
        </div>
        <span>{answeredCount}/{total} 已回答</span>
      </div>

      {/* 题目 */}
      <div className="gen-question-card">
        <div className="gen-q-num">Q{currentIdx + 1}</div>
        <div className="gen-q-text">{q.question}</div>

        {/* 选项 */}
        {q.type === 'choice' && Array.isArray(q.options) && (
          <div className="gen-options">
            {q.options.map((opt, i) => (
              <button
                key={i}
                className={`gen-option-btn ${answered === opt ? 'selected' : ''}`}
                onClick={() => setAns(opt)}
              >
                <span className="gen-opt-letter">{String.fromCharCode(65 + i)}</span>
                <span>{opt}</span>
              </button>
            ))}
          </div>
        )}

        {/* 开放题 */}
        {q.type === 'open' && (
          <textarea
            className="settings-input"
            style={{ minHeight:80, marginTop:12 }}
            placeholder="写下你的想法…（可以随意，没有对错）"
            value={answered || ''}
            onChange={e => setAns(e.target.value)}
          />
        )}
      </div>

      {error && <div className="gen-error">{error}</div>}

      {/* 导航 */}
      <div className="gen-quiz-nav">
        <div className="gen-nav-dots">
          {questions.map((_, i) => (
            <button
              key={i}
              className={`gen-dot ${i === currentIdx ? 'current' : answers[questions[i].id ?? i] ? 'done' : ''}`}
              onClick={() => setCurrentIdx(i)}
            />
          ))}
        </div>

        <div style={{ display:'flex', gap:8 }}>
          {currentIdx > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={() => setCurrentIdx(i => i - 1)}>← 上一题</button>
          )}
          {!isLast ? (
            <button className="btn btn-primary btn-sm"
              onClick={() => setCurrentIdx(i => i + 1)}
              disabled={!answered}>
              下一题 →
            </button>
          ) : (
            <button className="btn btn-primary"
              onClick={onGenerate}
              disabled={answeredCount < Math.ceil(total * 0.6)}
              title={answeredCount < Math.ceil(total * 0.6) ? `至少回答 ${Math.ceil(total * 0.6)} 题` : ''}>
              ✨ 生成主角
            </button>
          )}
        </div>
      </div>

      <div style={{ fontSize:11, color:'var(--text-dim)', textAlign:'center', marginTop:4 }}>
        已回答 {answeredCount}/{total} 题 · 至少需要 {Math.ceil(total * 0.6)} 题 · 点导航点可跳跃
      </div>
    </div>
  );
}

// ── 生成中 ────────────────────────────────────────────────────────────────────
function GeneratingPhase({ progress }) {
  return (
    <div className="gen-phase-body gen-loading">
      <div className="gen-spinner-wrap">
        <div className="gen-big-spinner" />
        <div className="gen-spinner-icon">✨</div>
      </div>
      <div className="gen-progress-text">{progress}</div>
      <div style={{ fontSize:12, color:'var(--text-dim)', marginTop:8 }}>
        正在调用 LLM 生成完整角色档案，预计 15-30 秒…
      </div>
    </div>
  );
}

// ── 预览 ──────────────────────────────────────────────────────────────────────
function PreviewPhase({ character: c, committed, error, generating, onBack, onRegenerate, onCommit, onChange }) {
  const [tab, setTab] = useState('basic');  // basic | psyche | stats | items | raw

  const [rawText, setRawText] = useState('');
  useEffect(() => {
    if (tab === 'raw') setRawText(JSON.stringify(c, null, 2));
  }, [tab]);

  if (!c) return null;

  const ATTR_LABELS = { STR:'力量', DUR:'耐力', VIT:'体质', REC:'恢复', AGI:'敏捷', REF:'反应', PER:'感知', MEN:'精神', SOL:'灵魂', CHA:'魅力' };
  const ITEM_LABELS = {
    ApplicationTechnique: '应用技巧', PassiveAbility: '被动能力',
    PowerSource: '力量基盘', Bloodline: '血统体质', Mech: '机甲',
    Inventory: '物品装备', Companion: '同伴', Knowledge: '知识理论', WorldTraverse: '世界坐标',
  };

  return (
    <div className="gen-preview">
      {/* 角色名片 */}
      <div className="gen-namecard">
        <div className="gen-avatar">
          {c.name?.charAt(0) || '?'}
        </div>
        <div className="gen-namecard-body">
          <div className="gen-char-name">{c.name || '未命名'}</div>
          <div className="gen-char-meta">
            {[c.gender, c.age ? c.age+'岁' : '', c.identity].filter(Boolean).join(' · ')}
          </div>
          <div className="gen-char-alignment">{c.alignment || ''}</div>
          <div className="gen-traits">
            {(c.traits || []).map((t, i) => (
              <span key={i} className="gen-trait-tag">{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* 标签页 */}
      <div className="gen-preview-tabs">
        {[
          ['basic','📖 基本'],['psyche','🧠 心理'],['stats','📊 面板'],
          ['items','🎒 物品'],
          ...(c.relationships?.length ? [['relations','👥 关系']] : []),
          ['raw','✏️ 高级编辑']
        ].map(([id,label]) => (
          <button key={id} className={`gen-preview-tab ${tab===id?'active':''}`}
            onClick={()=>setTab(id)}>{label}</button>
        ))}
      </div>

      <div className="gen-preview-body">
        {tab === 'basic' && (
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            <PreviewBlock title="外貌" icon="👤">
              <p className="gen-text">{c.appearance}</p>
              {c.clothing && <p className="gen-text" style={{color:'var(--text-secondary)'}}>着装：{c.clothing}</p>}
            </PreviewBlock>
            <PreviewBlock title="背景故事" icon="📖">
              <p className="gen-text">{c.background}</p>
            </PreviewBlock>
            <PreviewBlock title="性格" icon="💫">
              <ul className="gen-list">{(c.personality||[]).map((p,i)=><li key={i}>{p}</li>)}</ul>
            </PreviewBlock>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
              <PreviewBlock title="缺陷" icon="⚡">
                <ul className="gen-list red">{(c.flaws||[]).map((f,i)=><li key={i}>{f}</li>)}</ul>
              </PreviewBlock>
              <PreviewBlock title="行为习惯" icon="🔄">
                <ul className="gen-list">{(c.quirks||[]).map((q,i)=><li key={i}>{q}</li>)}</ul>
              </PreviewBlock>
              <PreviewBlock title="渴望" icon="💎">
                <ul className="gen-list gold">{(c.desires||[]).map((d,i)=><li key={i}>{d}</li>)}</ul>
              </PreviewBlock>
              <PreviewBlock title="恐惧" icon="☁️">
                <ul className="gen-list dim">{(c.fears||[]).map((f,i)=><li key={i}>{f}</li>)}</ul>
              </PreviewBlock>
            </div>
          </div>
        )}

        {tab === 'psyche' && c.psyche_model && (
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            {Object.entries(c.psyche_model.dimensions||{}).map(([catKey, axes]) => (
              <PreviewBlock key={catKey} title={{social:'社交',emotional:'情绪',cognitive:'认知',values:'价值观'}[catKey]||catKey} icon="📐">
                <div style={{display:'flex',flexDirection:'column',gap:6}}>
                  {Object.entries(axes).map(([axKey, val]) => (
                    <DimensionBar key={axKey} label={axKey} value={val} />
                  ))}
                </div>
              </PreviewBlock>
            ))}
            {(c.psyche_model.triggerPatterns||[]).length > 0 && (
              <PreviewBlock title="触发模式" icon="⚠️">
                {c.psyche_model.triggerPatterns.map((tp, i) => (
                  <div key={i} className="gen-trigger">
                    <span className="gen-trigger-t">触发：{tp.trigger}</span>
                    <span className="gen-trigger-r">反应：{tp.reaction}</span>
                    <span className="gen-trigger-i">强度 {tp.intensity}/10</span>
                  </div>
                ))}
              </PreviewBlock>
            )}
          </div>
        )}

        {tab === 'stats' && (
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            <PreviewBlock title="核心属性" icon="⚔️">
              <div className="gen-attr-grid">
                {Object.entries(c.attributes||{}).map(([k,v]) => (
                  <div key={k} className="gen-attr-cell">
                    <span className="gen-attr-label" title={k}>{ATTR_LABELS[k]||k}</span>
                    <div className="gen-attr-bar-wrap">
                      <div className="gen-attr-bar" style={{width:`${Math.min(100,(v/2)*100)}%`,
                        background: v>1.2?'var(--accent-green)':v<0.8?'var(--accent-rose)':'var(--accent-blue)'}} />
                    </div>
                    <span className="gen-attr-val">{Number(v).toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </PreviewBlock>
            {(c.knowledge||[]).length > 0 && (
              <PreviewBlock title="知识图谱" icon="📚">
                {c.knowledge.map((k,i) => (
                  <div key={i} className="gen-knowledge-row">
                    <span className="gen-k-name">{k.topic}</span>
                    <span className="gen-k-mastery">{k.mastery}</span>
                    {k.summary && <span className="gen-k-summary">{k.summary}</span>}
                  </div>
                ))}
              </PreviewBlock>
            )}
            {(c.powerSources||[]).length > 0 && (
              <PreviewBlock title="力量基盘" icon="⚡">
                {c.powerSources.map((ps,i) => (
                  <div key={i} className="gen-power-row">
                    <span className="gen-p-name">{ps.name}</span>
                    <span className="gen-p-grade">资质 {ps.aptitudeGrade||'C'}</span>
                    <span className="gen-p-realm">{ps.realm||'入门'}</span>
                  </div>
                ))}
              </PreviewBlock>
            )}
          </div>
        )}

        {tab === 'items' && (
          <div>
            {(c.startingItems||[]).length > 0 ? (
              <PreviewBlock title="初始随身物品" icon="🎒">
                {c.startingItems.map((item,i) => (
                  <div key={i} className="gen-item-row">
                    <span className="gen-item-name">{item.name}</span>
                    <span className="gen-item-type">{ITEM_LABELS[item.type] || item.type}</span>
                    {item.desc && <span className="gen-item-desc">{item.desc}</span>}
                  </div>
                ))}
              </PreviewBlock>
            ) : (
              <div style={{textAlign:'center',color:'var(--text-dim)',padding:24}}>
                该角色无初始物品
              </div>
            )}
          </div>
        )}

        {tab === 'relations' && (
          <div style={{display:'flex',flexDirection:'column',gap:10}}>
            {(c.relationships||[]).length === 0 ? (
              <div style={{textAlign:'center',color:'var(--text-dim)',padding:24}}>背景中无明确关联人物</div>
            ) : (
              (c.relationships||[]).map((rel, i) => {
                const EMOTION_COLORS = {
                  family:'#f97316', romance:'#ec4899', friendship:'#22c55e',
                  hostile:'#ef4444', affiliated:'#a78bfa', mixed:'#f59e0b',
                };
                const EMOTION_LABELS = {
                  family:'亲情', romance:'爱情', friendship:'友情',
                  hostile:'敌对', affiliated:'从属', mixed:'混合',
                };
                const color = EMOTION_COLORS[rel.emotion_type] || 'var(--accent-blue)';
                const affinity = rel.affinity ?? 50;
                return (
                  <div key={i} style={{
                    background:'rgba(255,255,255,0.03)',
                    border:`1px solid ${color}44`,
                    borderLeft:`3px solid ${color}`,
                    borderRadius:6, padding:'10px 14px',
                  }}>
                    <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:6}}>
                      <span style={{fontWeight:700,fontSize:14}}>{rel.name}</span>
                      <span style={{background:`${color}22`,color,borderRadius:12,padding:'2px 8px',fontSize:11}}>
                        {EMOTION_LABELS[rel.emotion_type] || rel.emotion_type}
                      </span>
                      {(rel.emotion_tags||[]).map((t,j) => (
                        <span key={j} style={{fontSize:10,color:'var(--text-dim)',background:'rgba(255,255,255,0.06)',borderRadius:8,padding:'1px 6px'}}>{t}</span>
                      ))}
                      <span style={{marginLeft:'auto',fontSize:11,color:'var(--text-secondary)'}}>{rel.npc_type}</span>
                    </div>
                    <div style={{fontSize:12,color:'var(--text-secondary)',marginBottom:6}}>
                      {rel.relation} · {rel.loyalty_type}
                    </div>
                    <div style={{marginBottom:6}}>
                      <div style={{display:'flex',alignItems:'center',gap:8}}>
                        <span style={{fontSize:11,color:'var(--text-dim)'}}>好感度</span>
                        <div style={{flex:1,height:4,borderRadius:2,background:'rgba(255,255,255,0.1)'}}>
                          <div style={{height:'100%',borderRadius:2,background:color,width:`${affinity}%`,transition:'width 0.3s'}} />
                        </div>
                        <span style={{fontSize:11,color}}>{affinity}</span>
                      </div>
                    </div>
                    {rel.background && <div style={{fontSize:11,color:'var(--text-dim)'}}>{rel.background}</div>}
                  </div>
                );
              })
            )}
          </div>
        )}

        {tab === 'raw' && (
          <div style={{display:'flex',flexDirection:'column',gap:8, height:'100%', minHeight:300}}>
            <div style={{fontSize:11, color:'var(--text-dim)'}}>
              提示：此为直接修改底层属性的极客模式。修改后只要 JSON 格式合法即可应用并被写入，保存时生效。
            </div>
            <textarea 
              className="input-field" 
              style={{flex:1, minHeight:300, fontFamily:'monospace', fontSize:12, resize:'vertical'}}
              value={rawText}
              onChange={(e) => {
                const val = e.target.value;
                setRawText(val);
                try {
                  const newC = JSON.parse(val);
                  onChange?.(newC);
                } catch(err) {
                  // Ignore parse err
                }
              }}
            />
          </div>
        )}
      </div>

      {error && <div className="gen-error" style={{margin:'0 16px 8px'}}>{error}</div>}

      {/* 底部操作 */}
      <div className="gen-preview-footer">
        {committed && generatedNpcs?.length > 0 && (
          <div style={{
            width:'100%', marginBottom:8, padding:'8px 12px',
            background:'rgba(34,197,94,0.08)', border:'1px solid rgba(34,197,94,0.3)',
            borderRadius:6, fontSize:12, color:'var(--accent-green)',
          }}>
            👥 已建立 {generatedNpcs.length} 个关联人物档案：{generatedNpcs.join('、')}
          </div>
        )}
        <button className="btn btn-ghost" onClick={onBack} disabled={generating || committed}>
          ← 返回修改
        </button>
        <button className="btn btn-ghost" onClick={onRegenerate} disabled={generating || committed}>
          🔄 重新随机生成
        </button>
        {committed ? (
          <button className="btn btn-primary" onClick={onDone}>
            ✓ 已写入 · 进入游戏
          </button>
        ) : (
          <button className="btn btn-primary" onClick={onCommit} disabled={generating}>
            {generating ? <><span className="spinner" /> 写入中…</> : '✨ 确认使用此主角'}
          </button>
        )}
      </div>
    </div>
  );
}

// ── 小工具 ────────────────────────────────────────────────────────────────────
function PreviewBlock({ title, icon, children }) {
  return (
    <div className="gen-block">
      <div className="gen-block-title">{icon} {title}</div>
      <div className="gen-block-body">{children}</div>
    </div>
  );
}

const AXIS_LABELS = {
  introExtro:'内倾←→外倾', trustRadius:'不信任←→信任', dominance:'顺从←→主导',
  empathy:'冷漠←→共情', boundaryStrength:'无边界←→强边界',
  stability:'动荡←→稳定', expressiveness:'压抑←→外放', recoverySpeed:'慢恢复←→快恢复',
  emotionalDepth:'肤浅←→深邃',
  analyticIntuitive:'直觉←→分析', openness:'封闭←→开放', riskTolerance:'规避←→嗜险',
  selfAwareness:'盲区大←→高度自知',
  autonomy:'顺从权威←→极端自主', altruism:'利己←→利他', rationality:'情绪←→理性',
  loyalty:'背信←→忠诚', idealism:'现实←→理想',
};

function DimensionBar({ label, value }) {
  const v   = Math.max(-10, Math.min(10, value || 0));
  const pct = ((v + 10) / 20) * 100;
  const color = v > 3 ? 'var(--accent-blue)' : v < -3 ? 'var(--accent-purple)' : 'var(--text-dim)';
  return (
    <div className="gen-dim-row">
      <span className="gen-dim-label" title={label}>{AXIS_LABELS[label]||label}</span>
      <div className="gen-dim-track">
        <div className="gen-dim-fill" style={{ left:`${Math.min(pct,50)}%`,
          width:`${Math.abs(pct-50)}%`, background:color }} />
        <div className="gen-dim-mid" />
        <div className="gen-dim-thumb" style={{ left:`${pct}%` }} />
      </div>
      <span className="gen-dim-val" style={{ color }}>{v > 0 ? '+' : ''}{v}</span>
    </div>
  );
}
