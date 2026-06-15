import { useState, useRef, useEffect } from 'react';
import { Input, Button, Typography, message, Dropdown, Tooltip } from 'antd';
import {
  SendOutlined, PlusOutlined,
  GlobalOutlined, EditOutlined, LinkOutlined,
  FileAddOutlined, WarningOutlined,
  DownOutlined, UpOutlined,
  BookOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { sendConversation, fetchAvailableModels, fetchKbCollections } from '@/api/client';
import { useStore } from '@/store';
import ShardFlowLogo from '@/components/common/ShardFlowLogo';
import KbSearchResults from '@/components/knowledge/KbSearchResults';
import { ContextPressureToast } from './ContextPressureToast';
import type { ChatMessage, StreamingPhase } from '@/types';

const { TextArea } = Input;
const { Text } = Typography;

/**
 * 企业级规范安全网：清除文本中残留的标签标记。
 * 处理完整标签（<THINKING>, </THINKING>, <ANSWER>, </ANSWER>）
 * 以及不完整标签（如 </THINKING, </ANSWER 等缺少 > 的变体）。
 */
const stripTagMarkers = (text: string): string => {
  if (!text) return text;
  // 完整标签（含空格变体）
  let result = text.replace(/<\/?THINKING\s*>/gi, '');
  result = result.replace(/<\/?ANSWER\s*>/gi, '');
  // 不完整标签（行尾缺少 > 的标签）
  result = result.replace(/<\/?THINKING[^>]*$/gi, '');
  result = result.replace(/<\/?ANSWER[^>]*$/gi, '');
  // 安全网：移除泄露的工具调用 JSON 块（```json {"action_plan": ...} ```）
  result = result.replace(/```json\s*\{\s*"action_plan"\s*:\s*\{[\s\S]*?\}\s*\}\s*```/gi, '');
  // 安全网：移除无代码围栏包裹的裸 action_plan JSON
  result = result.replace(/\{\s*"action_plan"\s*:\s*\{[\s\S]*?\}\s*\}/gi, '');
  return result;
};

interface Props {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

/** Phase labels shown in the streaming progress indicator */
const PHASE_LABELS: Record<string, string> = {
  intent: '识别意图',
  think: '思考中',
  action: '调用工具',
  observe: '观察结果',
  progress: '推理进度',
  answer: '生成回答',
  done: '完成',
};

export default function ChatPanel({ onLoginRequired, isAuthenticated }: Props) {
  const {
    messages, addMessage, isStreaming, setStreaming,
    streamingPhase, setStreamingPhase,
    abortController, setAbortController,
    activeTaskId, activeSessionId, updateMessage,
    kbSearchResults, clearKbSearchResults,
    kbActiveMount, setKbActiveMount, kbCollections, setKbCollections,
    setContextPressure,
  } = useStore();
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState(() => {
    return localStorage.getItem('shardflow_selected_model') || '';
  });
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);
  const [systemModels, setSystemModels] = useState<Array<{ key: string; label: string; provider?: string; model?: string; capabilities?: string; context_window?: number; type?: string; is_verified?: boolean }>>([]);
  const [thinkingExpanded, setThinkingExpanded] = useState<Record<string, boolean>>({});
  const [currentPhaseLabel, setCurrentPhaseLabel] = useState('');
  const [memoryContext, setMemoryContext] = useState<{context_shard_info: string; profile_context: string; episodic_context: string; has_memory: boolean} | null>(null);
  const [memoryPanelExpanded, setMemoryPanelExpanded] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);
  const streamingMsgIdRef = useRef<string>('');

  const hasMessages = messages.length > 0;

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    fetchAvailableModels()
      .then((models) => {
        if (models?.length) {
          setSystemModels(models);
          // 如果已选的模型不在可用列表中（如被删除或数据库迁移后），清除选择
          if (selectedModel && !models.find(m => m.key === selectedModel)) {
            setSelectedModel('');
          }
          if (!selectedModel) {
            const firstModel = models[0].key;
            setSelectedModel(firstModel);
            localStorage.setItem('shardflow_selected_model', firstModel);
          }
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchKbCollections()
      .then((cols) => {
        const list = Array.isArray(cols) ? cols : [];
        setKbCollections(list);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (plusMenuOpen && inputAreaRef.current && !inputAreaRef.current.contains(e.target as Node)) {
        setPlusMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [plusMenuOpen]);

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;
    if (!isAuthenticated) { onLoginRequired(); return; }

    if (isUnverifiedCustom) {
      message.warning('当前模型未通过连通性验证，请先在"模型"页面验证模型');
      return;
    }

    const effectiveTaskId = activeTaskId || `task-${Date.now()}`;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: input, timestamp: Date.now() };
    addMessage(userMsg);
    setInput('');
    setStreaming(true);
    setStreamingPhase('thinking');

    const controller = new AbortController();
    setAbortController(controller);

    const assistantMsgId = (Date.now() + 1).toString();
    streamingMsgIdRef.current = assistantMsgId;
    let assistantContent = '';
    let thinkingContent = '';
    let hasStreamingContent = false;
    let assistantCreated = false;

    // RAF-based rendering throttle: accumulate chunks between frames,
    // flush to store once per animation frame for smooth typewriter effect.
    let pendingAnswer = '';
    let pendingThink = '';
    let rafId: number | null = null;

    const flushToStore = () => {
      rafId = null;
      const updates: Partial<ChatMessage> = {};
      if (pendingThink) {
        thinkingContent += pendingThink;
        pendingThink = '';
        updates.thinkingContent = thinkingContent;
      }
      if (pendingAnswer) {
        assistantContent += pendingAnswer;
        pendingAnswer = '';
        updates.content = assistantContent;
        updates.streamingPhase = 'answering';
      }
      if (Object.keys(updates).length > 0) {
        updateMessage(assistantMsgId, updates);
      }
    };

    const scheduleFlush = () => {
      if (rafId === null) {
        rafId = requestAnimationFrame(flushToStore);
      }
    };

    await sendConversation(
      effectiveTaskId, userMsg.content, activeSessionId || '', selectedModel,
      (event: { type: string; data: Record<string, unknown> }) => {
        const data = event.data || {};

        // Update phase indicator
        const phaseLabel = PHASE_LABELS[event.type];
        if (phaseLabel) {
          setCurrentPhaseLabel(phaseLabel);
        }

        if (event.type === 'intent') {
          return;
        }

        if (event.type === 'context_pressure') {
          setContextPressure({
            level: (data.level as string) || 'warning',
            usage_ratio: (data.usage_ratio as number) || 0,
            message: (data.message as string) || '',
          });
          return;
        }

        if (event.type === 'session_switching') {
          const newSessionId = (data.new_session_id as string) || '';
          if (newSessionId && activeTaskId) {
            window.location.reload();
          }
          return;
        }

        // 3D-03: memory_context 事件 — 展示记忆注入摘要
        if (event.type === 'memory_context') {
          const hasMemory = data.has_memory as boolean;
          if (hasMemory) {
            setMemoryContext({
              context_shard_info: (data.context_shard_info as string) || '',
              profile_context: (data.profile_context as string) || '',
              episodic_context: (data.episodic_context as string) || '',
              has_memory: hasMemory,
            });
          }
          return;
        }

        // kb_search events: store knowledge base search results for display
        if (event.type === 'kb_search') {
          const results = (data.results as Array<Record<string, unknown>>) || [];
          if (results.length > 0 && assistantCreated) {
            updateMessage(assistantMsgId, {
              kbSearchResults: results.map((r) => ({
                title: (r.title as string) || '',
                snippet: (r.snippet as string) || '',
                relevance_score: (r.relevance_score as number) || 0,
                source: 'knowledge_base' as const,
                url: (r.url as string) || '',
                metadata: {
                  document_id: ((r.metadata as Record<string, unknown>)?.document_id as string) || '',
                  collection_name: ((r.metadata as Record<string, unknown>)?.collection_name as string) || '',
                  chunk_index: ((r.metadata as Record<string, unknown>)?.chunk_index as number) || 0,
                  node_id: ((r.metadata as Record<string, unknown>)?.node_id as string) || '',
                },
              })),
            });
          }
          return;
        }

        // think events: accumulate thinking content for collapsible display
        if (event.type === 'think') {
          const chunk = (data.reasoning as string) || '';
          if (!assistantCreated) {
            assistantCreated = true;
            addMessage({
              id: assistantMsgId,
              role: 'assistant',
              content: '',
              eventType: 'think',
              streamingPhase: 'thinking',
              thinkingContent: '',
              timestamp: Date.now(),
            });
          }
          if (chunk) {
            pendingThink += chunk;
            scheduleFlush();
          }
          return;
        }

        // answer events: accumulate chunks and flush once per animation frame
        if (event.type === 'answer') {
          const chunk = (data.content as string) || '';
          if (chunk) {
            hasStreamingContent = true;
            if (!assistantCreated) {
              assistantCreated = true;
              addMessage({
                id: assistantMsgId,
                role: 'assistant',
                content: '',
                eventType: 'answer',
                streamingPhase: 'answering',
                thinkingContent: '',
                timestamp: Date.now(),
              });
              setStreamingPhase('answering');
            }
            pendingAnswer += chunk;
            scheduleFlush();
          }
          return;
        }

        if (event.type === 'done') {
          // Cancel any pending RAF and flush immediately
          if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
          }
          if (pendingThink) {
            thinkingContent += pendingThink;
            pendingThink = '';
          }
          if (pendingAnswer) {
            assistantContent += pendingAnswer;
            pendingAnswer = '';
          }

          if (hasStreamingContent) {
            updateMessage(assistantMsgId, {
              content: assistantContent,
              thinkingContent: thinkingContent || undefined,
              eventType: 'done',
              streamingPhase: 'done',
            });
          } else {
            const answer = data.answer as string || '';
            if (answer) {
              assistantContent = answer;
            } else if (!assistantContent) {
              assistantContent = '任务已完成，但未生成回答内容。';
            }
            updateMessage(assistantMsgId, {
              content: assistantContent,
              thinkingContent: thinkingContent || undefined,
              eventType: 'done',
              streamingPhase: 'done',
            });
          }
          return;
        }
      },
      (err) => {
        if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
        addMessage({ id: (Date.now() + 2).toString(), role: 'system', content: `Error: ${err.message}`, eventType: 'error', timestamp: Date.now() });
        setStreaming(false);
        setStreamingPhase('idle');
        setAbortController(null);
      },
      () => {
        if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
        setStreaming(false);
        setStreamingPhase('idle');
        setAbortController(null);
        setCurrentPhaseLabel('');
      },
      controller.signal,
    );
  };

  const handleStop = () => {
    if (abortController) {
      abortController.abort();
      setStreaming(false);
      setStreamingPhase('idle');
      setAbortController(null);
      setCurrentPhaseLabel('');
    }
  };

  const toggleThinking = (msgId: string) => {
    setThinkingExpanded(prev => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  const extractContent = (type: string, data: Record<string, unknown>): string => {
    switch (type) {
      case 'action':
        // 企业级规范: 不暴露工具名称和参数，仅显示"正在获取信息"
        return '**🔍 正在获取信息...**\n\n';
      case 'observe': {
        // 企业级规范: 不暴露工具名、耗时，仅展示结果摘要
        const success = data.success !== false;
        if (!success) {
          // 工具失败时不暴露失败细节，仅提示用户
          return '> 注：部分信息获取受限，以下回答基于已有知识体系。\n\n';
        }
        // 成功时不展示原始结果，由最终答案整合呈现
        return '';
      }
      case 'done': case 'answer': return '';
      case 'intent': case 'think': case 'progress': case 'heartbeat': return '';
      default: return '';
    }
  };

  // Model options come entirely from the database via fetchAvailableModels() API
  const modelOptions = systemModels.map((m) => ({
    key: m.key,
    label: m.label,
    type: (m.type === 'custom' ? 'custom' : 'builtin') as 'builtin' | 'custom',
    verified: m.type === 'custom' ? !!m.is_verified : true,
  }));

  const builtinModelOptions = modelOptions.filter(m => m.type === 'builtin');
  const customModelOptions = modelOptions.filter(m => m.type === 'custom');

  const modelMenuItems = [];
  if (builtinModelOptions.length > 0) {
    modelMenuItems.push({
      type: 'group' as const,
      label: (
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)', display: 'block', padding: '4px 0' }}>
          内置模型
        </span>
      ),
      children: builtinModelOptions.map(m => ({
        key: m.key,
        label: (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {m.label}
          </span>
        ),
        onClick: () => {
          setSelectedModel(m.key);
          localStorage.setItem('shardflow_selected_model', m.key);
        },
      })),
    });
  }
  if (builtinModelOptions.length > 0 && customModelOptions.length > 0) {
    modelMenuItems.push({ type: 'divider' as const });
  }
  if (customModelOptions.length > 0) {
    modelMenuItems.push({
      type: 'group' as const,
      label: (
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--ink)', display: 'block', padding: '4px 0' }}>
          自定义模型
        </span>
      ),
      children: customModelOptions.map(m => ({
        key: m.key,
        label: (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {m.label}
            {!m.verified && (
              <WarningOutlined style={{ color: '#faad14', fontSize: 12 }} />
            )}
          </span>
        ),
        onClick: () => {
          setSelectedModel(m.key);
          localStorage.setItem('shardflow_selected_model', m.key);
        },
      })),
    });
  }

  const currentModel = modelOptions.find(m => m.key === selectedModel);
  const currentModelLabel = currentModel?.label || '';
  const isUnverifiedCustom = currentModel?.type === 'custom' && !currentModel?.verified;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      position: 'relative',
    }}>
      <ContextPressureToast />
      {/* 3D-03: 记忆注入提示展示（可选折叠面板） */}
      {memoryContext && memoryContext.has_memory && (
        <div style={{
          maxWidth: 900,
          margin: '8px auto 0',
          width: '100%',
          padding: '0 20px',
        }}>
          <div style={{
            background: 'rgba(201,168,124,0.06)',
            border: '1px solid rgba(201,168,124,0.2)',
            borderRadius: 10,
            overflow: 'hidden',
            fontSize: 12,
          }}>
            <button
              onClick={() => setMemoryPanelExpanded(!memoryPanelExpanded)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '6px 12px',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 12,
                color: 'var(--ink-faint)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {memoryPanelExpanded ? <UpOutlined style={{ fontSize: 10 }} /> : <DownOutlined style={{ fontSize: 10 }} />}
              <span>记忆上下文已注入</span>
            </button>
            {memoryPanelExpanded && (
              <div style={{
                padding: '4px 12px 8px',
                maxHeight: 150,
                overflow: 'auto',
                fontSize: 11,
                lineHeight: 1.6,
                color: 'var(--ink-faint)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}>
                {memoryContext.context_shard_info && (
                  <div style={{ marginBottom: 4 }}>
                    <strong>会话状态：</strong>{memoryContext.context_shard_info.slice(0, 300)}
                  </div>
                )}
                {memoryContext.profile_context && (
                  <div style={{ marginBottom: 4 }}>
                    <strong>用户画像：</strong>{memoryContext.profile_context.slice(0, 200)}
                  </div>
                )}
                {memoryContext.episodic_context && (
                  <div>
                    <strong>情景记忆：</strong>{memoryContext.episodic_context.slice(0, 200)}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      <div style={{
        flex: 1,
        overflow: 'auto',
        paddingBottom: 16,
        display: 'flex',
        flexDirection: 'column',
      }}>
        {!hasMessages ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            flex: 1,
            textAlign: 'center',
            paddingBottom: 120,
          }}>
            <div style={{
              width: 56,
              height: 56,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 24,
            }}>
              <ShardFlowLogo size={56} />
            </div>
            <h1 className="cn-title" style={{
              fontWeight: 600,
              color: 'var(--ink)',
              marginBottom: 12,
              letterSpacing: '0.05em',
              fontSize: 40,
            }}>
              ShardFlow
            </h1>
            <p className="cn-tag" style={{ fontSize: 14, marginBottom: 32 }}>
              你的专属助理
            </p>
          </div>
        ) : (
          <div style={{
            maxWidth: 900,
            margin: '0 auto',
            width: '100%',
            padding: '20px 20px 0',
            flex: 1,
          }}>
            {messages.map((msg) => (
              <div key={msg.id} className="message-enter" style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 20,
              }}>
                {msg.role === 'user' ? (
                  <div style={{
                    background: 'var(--ink)',
                    color: 'var(--paper)',
                    borderRadius: '16px 16px 4px 16px',
                    padding: '10px 16px',
                    maxWidth: '75%',
                    fontSize: 14,
                    lineHeight: '1.7',
                    letterSpacing: '0.02em',
                    fontFamily: 'var(--font-serif)',
                  }}>
                    {msg.content}
                  </div>
                ) : msg.role === 'system' ? (
                  <Text type="danger" style={{ fontSize: 13 }}>{msg.content}</Text>
                ) : (
                  <div style={{ width: '100%' }}>
                    {/* Thinking section - collapsible, default hidden per enterprise spec */}
                    {msg.thinkingContent && (
                      <div className="thinking-section" style={{
                        marginBottom: msg.content ? 8 : 0,
                        borderRadius: 10,
                        border: '1px solid var(--paper-dark)',
                        overflow: 'hidden',
                        transition: 'all 0.3s ease',
                      }}>
                        <button
                          onClick={() => toggleThinking(msg.id)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            width: '100%',
                            padding: '6px 12px',
                            border: 'none',
                            background: 'rgba(201,168,124,0.06)',
                            cursor: 'pointer',
                            fontSize: 12,
                            color: 'var(--ink-faint)',
                            fontFamily: 'var(--font-sans)',
                            letterSpacing: '0.04em',
                            transition: 'background 0.2s ease',
                          }}
                          onMouseEnter={(e) => {
                            (e.currentTarget as HTMLElement).style.background = 'rgba(201,168,124,0.12)';
                          }}
                          onMouseLeave={(e) => {
                            (e.currentTarget as HTMLElement).style.background = 'rgba(201,168,124,0.06)';
                          }}
                        >
                          {thinkingExpanded[msg.id] ? <UpOutlined style={{ fontSize: 10 }} /> : <DownOutlined style={{ fontSize: 10 }} />}
                          <span>推理过程</span>
                          {isStreaming && msg.id === streamingMsgIdRef.current && msg.streamingPhase === 'thinking' && (
                            <span className="thinking-pulse" style={{
                              display: 'inline-block',
                              width: 6,
                              height: 6,
                              borderRadius: '50%',
                              background: 'var(--accent-warm)',
                              marginLeft: 4,
                            }} />
                          )}
                        </button>
                        {thinkingExpanded[msg.id] && (
                          <div style={{
                            padding: '6px 12px',
                            maxHeight: 200,
                            overflow: 'auto',
                            fontSize: 12,
                            lineHeight: 1.6,
                            color: 'var(--ink-faint)',
                            fontFamily: 'var(--font-mono)',
                            background: 'rgba(0,0,0,0.02)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-all',
                          }}>
                            <div style={{
                              fontSize: 11,
                              color: 'var(--ink-faint)',
                              opacity: 0.7,
                              marginBottom: 6,
                              fontStyle: 'italic',
                            }}>
                              以下为内部推理过程，可能包含未验证信息
                            </div>
                            {stripTagMarkers(msg.thinkingContent)}
                            {isStreaming && msg.id === streamingMsgIdRef.current && msg.streamingPhase === 'thinking' && (
                              <span className="streaming-cursor" style={{
                                display: 'inline-block',
                                width: 2,
                                height: '1em',
                                background: 'var(--ink-faint)',
                                marginLeft: 2,
                                verticalAlign: 'text-bottom',
                                animation: 'blink 0.8s step-end infinite',
                              }} />
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Answer content */}
                    <div style={{
                      background: 'rgba(255,255,255,0.6)',
                      border: '1px solid var(--paper-dark)',
                      borderRadius: '16px 4px 16px 16px',
                      padding: msg.content ? '13px 18px' : '11px 18px',
                      color: 'var(--ink-soft)',
                      fontSize: 15,
                      lineHeight: '1.7',
                      maxWidth: '100%',
                      letterSpacing: '0.02em',
                      position: 'relative',
                      transition: 'all 0.3s ease',
                    }}>
                      <div style={{
                        position: 'absolute',
                        bottom: -3,
                        left: '2%',
                        right: '2%',
                        height: 3,
                        background: 'var(--paper-dark)',
                        borderRadius: '0 0 4px 4px',
                        opacity: 0.3,
                      }} />
                      {msg.content ? (
                        <div className="markdown-body">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{stripTagMarkers(msg.content)}</ReactMarkdown>
                        </div>
                      ) : null}
                      {/* Knowledge base search results for this message */}
                      {msg.kbSearchResults && msg.kbSearchResults.length > 0 && (
                        <KbSearchResults results={msg.kbSearchResults} />
                      )}
                      {isStreaming && msg.id === streamingMsgIdRef.current && msg.streamingPhase === 'answering' && (
                        <span className="streaming-cursor" style={{
                          display: 'inline-block',
                          width: 2,
                          height: '1em',
                          background: 'var(--ink)',
                          marginLeft: 2,
                          verticalAlign: 'text-bottom',
                          animation: 'blink 0.8s step-end infinite',
                        }} />
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {/* Streaming progress indicator */}
            {isStreaming && (() => {
              const streamingMsg = messages.find(m => m.role === 'assistant' && m.id === streamingMsgIdRef.current);
              const isThinking = !streamingMsg || streamingMsg.streamingPhase === 'thinking';
              const isAnswering = streamingMsg?.streamingPhase === 'answering';

              return (
                <div className="message-enter" style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
                  <div style={{ flexShrink: 0 }}>
                    <div style={{
                      width: 36,
                      height: 36,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <ShardFlowLogo size={36} />
                    </div>
                  </div>
                  <div style={{
                    background: 'rgba(255,255,255,0.6)',
                    border: '1px solid var(--paper-dark)',
                    borderRadius: '16px 4px 16px 16px',
                    padding: '12px 18px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 12,
                  }}>
                    {isThinking && (
                      <>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <div className="typing-dot" />
                          <div className="typing-dot" />
                          <div className="typing-dot" />
                        </div>
                        <span className="cn-tag" style={{ fontSize: 13 }}>
                          {currentPhaseLabel || '正在思考...'}
                        </span>
                      </>
                    )}
                    {isAnswering && (
                      <div className="streaming-progress" style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}>
                        <div style={{
                          width: 120,
                          height: 3,
                          background: 'var(--paper-dark)',
                          borderRadius: 2,
                          overflow: 'hidden',
                        }}>
                          <div className="progress-bar" style={{
                            height: '100%',
                            background: 'var(--accent)',
                            borderRadius: 2,
                            animation: 'progressPulse 2s ease-in-out infinite',
                          }} />
                        </div>
                        <span className="cn-tag" style={{ fontSize: 12 }}>
                          生成回答中
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            <div ref={messagesEnd} />
          </div>
        )}
      </div>

      <div style={{
        padding: '0 24px 26px',
      }}>
        <div
          ref={inputAreaRef}
          style={{
            maxWidth: 900,
            margin: '0 auto',
            width: '100%',
            position: 'relative',
          }}
        >
          {plusMenuOpen && (
            <div style={{
              position: 'absolute',
              bottom: '100%',
              left: 0,
              marginBottom: 8,
              background: 'rgba(255,255,255,0.95)',
              border: '1px solid var(--paper-dark)',
              borderRadius: 12,
              padding: '8px 6px',
              boxShadow: '0 4px 20px var(--shadow)',
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              minWidth: 180,
              zIndex: 10,
              animation: 'sketchIn 0.2s ease forwards',
            }}>
              <Tooltip title="支持 .docx、.pdf、.txt、.md 等格式" placement="right">
                <button
                  className="cn-sans"
                  onClick={() => {
                    setPlusMenuOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: 'none',
                    background: 'transparent',
                    color: 'var(--ink-soft)',
                    cursor: 'pointer',
                    fontSize: 14,
                    letterSpacing: '0.04em',
                    transition: 'all 0.2s ease',
                    width: '100%',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.6)';
                    (e.currentTarget as HTMLElement).style.color = 'var(--ink)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                    (e.currentTarget as HTMLElement).style.color = 'var(--ink-soft)';
                  }}
                >
                  <FileAddOutlined style={{ fontSize: 16, color: 'var(--accent-warm)' }} />
                  添加文件
                </button>
              </Tooltip>
              <Tooltip title="开启后，AI 将自动搜索互联网获取最新信息" placement="right">
                <button
                  className="cn-sans"
                  onClick={() => {
                    setWebSearchEnabled(!webSearchEnabled);
                    setPlusMenuOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: 'none',
                    background: webSearchEnabled ? 'rgba(201,168,124,0.1)' : 'transparent',
                    color: webSearchEnabled ? 'var(--accent-warm)' : 'var(--ink-soft)',
                    cursor: 'pointer',
                    fontSize: 14,
                    letterSpacing: '0.04em',
                    transition: 'all 0.2s ease',
                    width: '100%',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => {
                    if (!webSearchEnabled) {
                      (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.6)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!webSearchEnabled) {
                      (e.currentTarget as HTMLElement).style.background = 'transparent';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-soft)';
                    }
                  }}
                >
                  <GlobalOutlined style={{ fontSize: 16, color: webSearchEnabled ? 'var(--accent-warm)' : 'var(--ink-faint)' }} />
                  联网搜索
                </button>
              </Tooltip>
              <Tooltip title="开启后，AI 将从知识库中检索相关文档辅助回答" placement="right">
                <button
                  className="cn-sans"
                  onClick={() => {
                    if (!kbActiveMount.mounted) {
                      const activeCols = (Array.isArray(kbCollections) ? kbCollections : []).filter((c) => c.status === 'ACTIVE');
                      if (activeCols.length > 0) {
                        setKbActiveMount({ mounted: true, collectionId: activeCols[0].id, collectionName: activeCols[0].name });
                      } else {
                        setKbActiveMount({ mounted: true });
                      }
                    } else {
                      setKbActiveMount({ mounted: false });
                    }
                    setPlusMenuOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: 'none',
                    background: kbActiveMount.mounted ? 'rgba(201,168,124,0.1)' : 'transparent',
                    color: kbActiveMount.mounted ? 'var(--accent-warm)' : 'var(--ink-soft)',
                    cursor: 'pointer',
                    fontSize: 14,
                    letterSpacing: '0.04em',
                    transition: 'all 0.2s ease',
                    width: '100%',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => {
                    if (!kbActiveMount.mounted) {
                      (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.6)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!kbActiveMount.mounted) {
                      (e.currentTarget as HTMLElement).style.background = 'transparent';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-soft)';
                    }
                  }}
                >
                  <BookOutlined style={{ fontSize: 16, color: kbActiveMount.mounted ? 'var(--accent-warm)' : 'var(--ink-faint)' }} />
                  知识库
                </button>
              </Tooltip>
            </div>
          )}

          <div style={{
            background: 'rgba(255,255,255,0.5)',
            border: '1px solid var(--paper-dark)',
            borderRadius: 20,
            padding: '10px 14px',
            width: '100%',
            transition: 'all 0.4s ease',
            position: 'relative',
          }}
          onFocus={(e) => {
            (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.8)';
            (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent)';
            (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 24px var(--shadow)';
          }}
          onBlur={(e) => {
            (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.5)';
            (e.currentTarget as HTMLElement).style.borderColor = 'var(--paper-dark)';
            (e.currentTarget as HTMLElement).style.boxShadow = 'none';
          }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <TextArea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder={isAuthenticated ? '输入你的问题...' : '登录后开始对话'}
                autoSize={{ minRows: 3, maxRows: 12 }}
                disabled={!isAuthenticated || isStreaming}
                style={{
                  border: 'none',
                  boxShadow: 'none',
                  background: 'transparent',
                  resize: 'none',
                  fontSize: 16,
                  lineHeight: '28px',
                  padding: '4px 0',
                  width: '100%',
                  fontFamily: 'var(--font-serif)',
                  letterSpacing: '0.02em',
                  color: 'var(--ink)',
                }}
              />

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Button
                    type="text"
                    icon={<PlusOutlined />}
                    onClick={() => setPlusMenuOpen(!plusMenuOpen)}
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 10,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      color: plusMenuOpen ? 'var(--accent-warm)' : 'var(--ink-faint)',
                      fontSize: 16,
                      transition: 'color 0.2s ease',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {isAuthenticated && (
                    <Dropdown
                      menu={{
                        items: modelMenuItems,
                        selectedKeys: [selectedModel],
                      }}
                      trigger={['click']}
                    >
                      <Button
                        type="text"
                        size="small"
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '4px 8px',
                          borderRadius: 8,
                          color: isUnverifiedCustom ? '#faad14' : 'var(--ink-faint)',
                          fontSize: 13,
                          height: 30,
                          fontFamily: 'var(--font-sans)',
                        }}
                      >
                        {isUnverifiedCustom && <WarningOutlined style={{ fontSize: 12 }} />}
                        {currentModelLabel}
                      </Button>
                    </Dropdown>
                  )}

                  <Tooltip title="优化你的输入内容，使其更清晰、更具体" placement="top">
                    <Button
                      type="text"
                      icon={<EditOutlined />}
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 10,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        color: 'var(--ink-faint)',
                        fontSize: 16,
                      }}
                    />
                  </Tooltip>

                  <Tooltip title="跨会话状态接续" placement="top">
                    <Button
                      type="text"
                      icon={<LinkOutlined />}
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 10,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        color: 'var(--ink-faint)',
                        fontSize: 16,
                      }}
                    />
                  </Tooltip>

                  {isStreaming ? (
                    <Tooltip title="终止对话" placement="top">
                      <button
                        onClick={handleStop}
                        style={{
                          width: 40,
                          height: 40,
                          borderRadius: 10,
                          background: 'var(--ink)',
                          color: 'var(--paper)',
                          border: 'none',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                          cursor: 'pointer',
                          transition: 'all 0.3s ease',
                          fontFamily: 'var(--font-sans)',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'var(--ink-soft)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'var(--ink)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                        }}
                      >
                        <div style={{
                          width: 12,
                          height: 12,
                          background: 'var(--paper)',
                          borderRadius: 2,
                        }} />
                      </button>
                    </Tooltip>
                  ) : (
                    <Tooltip title="发送" placement="top">
                      <button
                        onClick={handleSend}
                        disabled={!input.trim() || !isAuthenticated}
                        style={{
                          width: 40,
                          height: 40,
                          borderRadius: 10,
                          background: input.trim() && isAuthenticated ? 'var(--ink)' : 'rgba(42,37,32,0.25)',
                          color: input.trim() && isAuthenticated ? 'var(--paper)' : 'rgba(255,255,255,0.5)',
                          border: 'none',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                          cursor: input.trim() && isAuthenticated ? 'pointer' : 'not-allowed',
                          transition: 'all 0.3s ease',
                          fontFamily: 'var(--font-sans)',
                        }}
                        onMouseEnter={(e) => {
                          if (input.trim() && isAuthenticated) {
                            (e.currentTarget as HTMLElement).style.background = 'var(--ink-soft)';
                            (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)';
                            (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(42,37,32,0.15)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (input.trim() && isAuthenticated) {
                            (e.currentTarget as HTMLElement).style.background = 'var(--ink)';
                            (e.currentTarget as HTMLElement).style.transform = 'translateY(0)';
                            (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                          }
                        }}
                      >
                        <SendOutlined style={{ fontSize: 16 }} />
                      </button>
                    </Tooltip>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
