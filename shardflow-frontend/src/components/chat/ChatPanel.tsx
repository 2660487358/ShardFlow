import { useState, useRef, useEffect } from 'react';
import { Input, Button, Typography, message, Dropdown, Tooltip } from 'antd';
import {
  SendOutlined, PlusOutlined,
  GlobalOutlined, EditOutlined,
  FileAddOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { sendConversation } from '@/api/client';
import { useStore } from '@/store';
import ShardFlowLogo from '@/components/common/ShardFlowLogo';
import type { ChatMessage, SSEEvent } from '@/types';

const { TextArea } = Input;
const { Text, Title } = Typography;

interface Props {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

const modelOptions = [
  { key: 'sf-2.5', label: 'SF 2.5 模型' },
  { key: 'sf-2.0', label: 'SF 2.0 模型' },
  { key: 'sf-1.5', label: 'SF 1.5 模型' },
];

export default function ChatPanel({ onLoginRequired, isAuthenticated }: Props) {
  const { messages, addMessage, isStreaming, setStreaming, activeTaskId, activeSessionId } = useStore();
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState('sf-2.5');
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const inputAreaRef = useRef<HTMLDivElement>(null);

  const hasMessages = messages.length > 0;

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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

    const effectiveTaskId = activeTaskId || `task-${Date.now()}`;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: input, timestamp: Date.now() };
    addMessage(userMsg);
    setInput('');
    setStreaming(true);

    const assistantMsgId = (Date.now() + 1).toString();
    let assistantContent = '';

    await sendConversation(
      effectiveTaskId, userMsg.content, activeSessionId || '',
      (event: { type: string; data: Record<string, unknown> }) => {
        const data = event.data || {};
        if (event.type === 'profile_applied') { message.info(`已应用偏好：${data.preferred_depth || '默认'}`); return; }
        if (event.type === 'done') return;
        const content = extractContent(event.type, data);
        assistantContent += content;
        const existing = useStore.getState().messages.find((m) => m.id === assistantMsgId);
        if (existing) {
          useStore.setState({
            messages: useStore.getState().messages.map((m) =>
              m.id === assistantMsgId ? { ...m, content: assistantContent } : m),
          });
        } else {
          addMessage({
            id: assistantMsgId, role: 'assistant', content: assistantContent,
            eventType: event.type as SSEEvent['type'], timestamp: Date.now(),
          });
        }
      },
      (err) => {
        addMessage({ id: (Date.now() + 2).toString(), role: 'system', content: `Error: ${err.message}`, eventType: 'error', timestamp: Date.now() });
        setStreaming(false);
      },
      () => setStreaming(false),
    );
  };

  const extractContent = (type: string, data: Record<string, unknown>): string => {
    switch (type) {
      case 'think': return data.reasoning ? `${data.reasoning}\n\n` : `${data.content || ''}\n\n`;
      case 'action': return `**🔧 调用工具**: ${data.tool || data.tool_name}\n\n`;
      case 'observe': {
        const success = data.success !== false;
        const icon = success ? '✅' : '❌';
        const toolName = data.tool || data.tool_name || 'unknown';
        return `${icon} **${toolName}**${data.latency_ms ? ` (${data.latency_ms}ms)` : ''}\n${data.result || data.snippet || ''}\n\n`;
      }
      case 'strategy': return `**📋 策略**: ${data.decision}${data.similarity ? ` (相似度 ${Number(data.similarity).toFixed(2)})` : ''}\n\n`;
      case 'done': return '';
      case 'intent': case 'progress': case 'shard_trigger': case 'shard_result': case 'shard_resume': case 'heartbeat': return '';
      default: return '';
    }
  };

  const currentModelLabel = modelOptions.find(m => m.key === selectedModel)?.label || 'SF 2.5 模型';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      position: 'relative',
    }}>
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
            maxWidth: 720,
            margin: '0 auto',
            width: '100%',
            padding: '24px 24px 0',
            flex: 1,
          }}>
            {messages.map((msg) => (
              <div key={msg.id} className="message-enter" style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 24,
              }}>
                {msg.role === 'user' ? (
                  <div style={{
                    background: 'var(--ink)',
                    color: 'var(--paper)',
                    borderRadius: '16px 16px 4px 16px',
                    padding: '12px 18px',
                    maxWidth: '80%',
                    fontSize: 14,
                    lineHeight: '1.9',
                    letterSpacing: '0.02em',
                    fontFamily: 'var(--font-serif)',
                  }}>
                    {msg.content}
                  </div>
                ) : msg.role === 'system' ? (
                  <Text type="danger" style={{ fontSize: 13 }}>{msg.content}</Text>
                ) : (
                  <div style={{
                    background: 'rgba(255,255,255,0.6)',
                    border: '1px solid var(--paper-dark)',
                    borderRadius: '16px 4px 16px 16px',
                    padding: '16px 20px',
                    color: 'var(--ink-soft)',
                    fontSize: 15,
                    lineHeight: '1.9',
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
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
            {isStreaming && (
              <div className="message-enter" style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
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
                  padding: '14px 20px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 12,
                }}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                  <span className="cn-tag" style={{ fontSize: 13 }}>正在思考...</span>
                </div>
              </div>
            )}
            <div ref={messagesEnd} />
          </div>
        )}
      </div>

      <div style={{
        padding: '0 24px 32px',
      }}>
        <div
          ref={inputAreaRef}
          style={{
            maxWidth: 720,
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
                {webSearchEnabled ? '联网搜索已开启' : '开启联网搜索'}
              </button>
            </div>
          )}

          <div style={{
            background: 'rgba(255,255,255,0.5)',
            border: '1px solid var(--paper-dark)',
            borderRadius: 20,
            padding: '8px 12px',
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
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
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

              <TextArea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder={isAuthenticated ? '输入你的问题...' : '登录后开始对话'}
                autoSize={{ minRows: 1, maxRows: 5 }}
                disabled={!isAuthenticated || isStreaming}
                style={{
                  border: 'none',
                  boxShadow: 'none',
                  background: 'transparent',
                  resize: 'none',
                  fontSize: 16,
                  lineHeight: '28px',
                  padding: '4px 0',
                  flex: 1,
                  fontFamily: 'var(--font-serif)',
                  letterSpacing: '0.02em',
                  color: 'var(--ink)',
                }}
              />

              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {webSearchEnabled && (
                  <Tooltip title="联网搜索已开启，点击关闭" placement="top">
                    <button
                      onClick={() => setWebSearchEnabled(false)}
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 10,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        fontSize: 16,
                        border: '1px solid var(--accent)',
                        background: 'rgba(201,168,124,0.1)',
                        color: 'var(--accent-warm)',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <GlobalOutlined />
                    </button>
                  </Tooltip>
                )}

                <Dropdown
                  menu={{
                    items: modelOptions.map(m => ({
                      key: m.key,
                      label: m.label,
                      onClick: () => setSelectedModel(m.key),
                    })),
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
                      color: 'var(--ink-faint)',
                      fontSize: 13,
                      height: 30,
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    {currentModelLabel}
                  </Button>
                </Dropdown>

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

                {input.trim() && isAuthenticated && (
                  <button
                    onClick={handleSend}
                    disabled={isStreaming}
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
                      cursor: isStreaming ? 'not-allowed' : 'pointer',
                      transition: 'all 0.3s ease',
                      fontFamily: 'var(--font-sans)',
                    }}
                    onMouseEnter={(e) => {
                      if (!isStreaming) {
                        (e.currentTarget as HTMLElement).style.background = 'var(--ink-soft)';
                        (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)';
                        (e.currentTarget as HTMLElement).style.boxShadow = '0 4px 12px rgba(42,37,32,0.15)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = 'var(--ink)';
                      (e.currentTarget as HTMLElement).style.transform = 'translateY(0)';
                      (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                    }}
                  >
                    <SendOutlined style={{ fontSize: 16 }} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        <p className="cn-tag" style={{ textAlign: 'center', fontSize: 12, color: 'var(--ink-muted)', marginTop: 12 }}>
          AI 助手可能会产生不准确的信息，请核实重要信息。
        </p>
      </div>
    </div>
  );
}
