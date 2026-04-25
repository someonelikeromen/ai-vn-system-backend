import { useState, useEffect, useRef, useCallback } from 'react';
import { api, streamMessage } from '../api.js';

// 模块级单调递增计数器，避免同毫秒内 ID 碰撞
let _msgSeq = 0;
const nextId = () => `msg_${Date.now()}_${++_msgSeq}`;

/**
 * useGame — 核心游戏状态 + SSE 管理 Hook
 */
export function useGame(novelId) {
  const [messages, setMessages]       = useState([]);
  const [isStreaming, setIsStreaming]  = useState(false);
  const [logEvents, setLogEvents]     = useState([]);
  const [grants, setGrants]           = useState([]);
  const [currentStep, setCurrentStep] = useState(-1);
  const controllerRef = useRef(null);
  const chapterIdRef  = useRef('');

  const addLog = useCallback((entry) => {
    setLogEvents(prev => [...prev.slice(-199), { id: Date.now() + Math.random(), ...entry }]);
  }, []);

  const sendMessage = useCallback(async (userInput) => {
    if (!novelId || !userInput.trim() || isStreaming) return;

    setIsStreaming(true);
    setGrants([]);
    setCurrentStep(0);

    // 立即显示用户输入
    const userMsgId = nextId();
    setMessages(prev => [...prev, { role: 'user', content: userInput, id: userMsgId }]);
    let aiContent = '';
    const aiMsgId = nextId();
    setMessages(prev => [...prev, { role: 'assistant', content: '', id: aiMsgId, streaming: true }]);

    controllerRef.current = streamMessage(
      novelId,
      userInput,
      chapterIdRef.current,
      (type, payload) => {
        switch (type) {
          case 'log':
            setCurrentStep(payload.step ?? 0);
            addLog({ type: 'log', step: payload.step, content: payload.content });
            break;
          case 'thought':
            addLog({ type: 'thought', agent: payload.agent, content: payload.content });
            break;
          case 'novel_text':
            aiContent = payload.content || '';
            setMessages(prev => prev.map(m =>
              m.id === aiMsgId ? { ...m, content: aiContent, streaming: true } : m
            ));
            break;
          case 'system_grant':
            setGrants(prev => [...prev, payload]);
            addLog({ type: 'grant', content: formatGrant(payload) });
            break;
          case 'error':
            addLog({ type: 'error', content: payload.content });
            break;
          case 'done':
            setMessages(prev => prev.map(m =>
              m.id === aiMsgId ? { ...m, streaming: false } : m
            ));
            addLog({ type: 'done', content: '✓ 回合完成' });
            setCurrentStep(-1);
            setIsStreaming(false);
            break;
          default: break;
        }
      }
    );
  }, [novelId, isStreaming, addLog]);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    setIsStreaming(false);
    setCurrentStep(-1);
  }, []);

  // 加载历史消息
  const loadMessages = useCallback(async () => {
    if (!novelId) return;
    try {
      const { messages: msgs } = await api.getMessages(novelId, 50);
      setMessages(
        [...msgs].reverse().map(m => ({
          id: m.id || Date.now() + Math.random(),
          role: m.role,
          content: m.display_content || m.raw_content || '',
        }))
      );
    } catch { /* ignore */ }
  }, [novelId]);

  useEffect(() => { loadMessages(); }, [loadMessages]);

  return {
    messages, isStreaming, logEvents, grants, currentStep,
    sendMessage, abort, loadMessages,
    setChapterId: (id) => { chapterIdRef.current = id; },
  };
}

function formatGrant(g) {
  switch (g.type) {
    case 'kill':   return `⚔️ 击${g.kill_type === 'kill' ? '杀' : '败'} ${g.tier}★${g.tier_sub}`;
    case 'xp':     return `📈 ${g.school} XP +${g.amount} [${g.context}]`;
    case 'points': return `💎 +${g.amount} 积分`;
    case 'stat':   return `📊 ${g.attr} ${g.delta > 0 ? '+' : ''}${g.delta}`;
    case 'energy': return `⚡ ${g.pool} ${g.delta}`;
    default:       return JSON.stringify(g);
  }
}

/**
 * useNovel — 小说管理 Hook
 */
export function useNovel() {
  const [novels, setNovels]     = useState([]);
  const [novel, setNovel]       = useState(null);
  const [protagonist, setProtagonist] = useState(null);
  const [hooks, setHooks]       = useState([]);
  const [loading, setLoading]   = useState(false);

  const loadNovels = useCallback(async () => {
    try {
      const { novels: list } = await api.listNovels();
      setNovels(list || []);
    } catch { /* ignore */ }
  }, []);

  const selectNovel = useCallback(async (id) => {
    try {
      setLoading(true);
      const [novelData, hooksData] = await Promise.all([
        api.getNovel(id).catch(() => null),
        api.getHooks(id).catch(() => ({ hooks: [] })),
      ]);
      setNovel(novelData?.novel ?? novelData);
      setHooks(hooksData.hooks || []);

      // getNovel 已返回 protagonist，尽量复用避免多余请求
      if (novelData?.protagonist) {
        // 补全 owned_items / medals / points（getNovel 返回的 protagonist 是简化版）
        const protFull = await api.getProtagonist(id).catch(() => null);
        setProtagonist(protFull ?? novelData.protagonist);
      } else {
        const protFull = await api.getProtagonist(id).catch(() => null);
        setProtagonist(protFull);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  const refreshProtagonist = useCallback(async (id) => {
    if (!id) return;
    try {
      const data = await api.getProtagonist(id);
      setProtagonist(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadNovels(); }, [loadNovels]);

  return {
    novels, novel, protagonist, hooks, loading,
    setNovel, loadNovels, selectNovel, refreshProtagonist, setHooks,
  };
}
