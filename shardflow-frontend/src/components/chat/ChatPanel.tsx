import { useState, useRef, useEffect } from 'react';
import { Input, Button, Typography, message } from 'antd';
import { SendOutlined, ThunderboltOutlined, ApiOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { sendConversation } from '@/api/client';
import { useStore } from '@/store';
import type { ChatMessage, SSEEvent } from '@/types';

const { TextArea } = Input;
const { Text, Title } = Typography;

interface Props {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function ChatPanel({ onLoginRequired, isAuthenticated }: Props) {
  const { messages, addMessage, isStreaming, setStreaming, activeTaskId, activeSessionId } = useStore();
  const [input, setInput] = useState('');
  const messagesEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
      case 'message': return `${data.content || ''}\n\n`;
      case 'tool_call_start': return `**🔧 调用工具**: ${data.tool_name}\n\n`;
      case 'tool_call_result': return `${data.success ? '✅' : '❌'} **${data.tool_name}** (${data.latency_ms}ms)\n${data.snippet || ''}\n\n`;
      case 'strategy_found': return `**📋 策略**: ${data.decision} (相似度 ${data.similarity})\n\n`;
      default: return '';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 16 }}>
        {messages.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', minHeight: '60vh', textAlign: 'center',
          }}>
            <Title level={2} style={{ fontWeight: 700, color: '#1a1a2e', marginBottom: 8 }}>
              有什么我可以帮你的？
            </Title>
            <Text style={{ fontSize: 15, color: '#9ca3af', marginBottom: 32 }}>
              ShardFlow 基于你的画像智能检索知识，提供个性化研究辅助
            </Text>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 24,
            }}>
              {msg.role === 'user' ? (
                <div style={{
                  background: '#4e7dff',
                  color: '#ffffff',
                  borderRadius: '12px 12px 4px 12px',
                  padding: '12px 16px',
                  maxWidth: '85%',
                  fontSize: 14,
                  lineHeight: '22px',
                  boxShadow: '0 1px 3px rgba(78,125,255,0.3)',
                }}>
                  {msg.content}
                </div>
              ) : msg.role === 'system' ? (
                <Text type="danger" style={{ fontSize: 13 }}>{msg.content}</Text>
              ) : (
                <div style={{
                  background: 'transparent',
                  color: '#1a1a2e',
                  fontSize: 15,
                  lineHeight: '26px',
                  maxWidth: '100%',
                }}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEnd} />
      </div>

      {/* Input */}
      <div style={{
        padding: '16px 0 24px',
        borderTop: messages.length > 0 ? 'none' : 'none',
      }}>
        <div style={{
          background: '#ffffff',
          border: `1px solid ${isAuthenticated ? '#e5e7eb' : '#e5e7eb'}`,
          borderRadius: 16,
          padding: '8px 8px 8px 20px',
          display: 'flex',
          alignItems: 'flex-end',
          gap: 8,
          boxShadow: isAuthenticated ? '0 0 0 0 rgba(78,125,255,0)' : 'none',
          transition: 'box-shadow 250ms, border-color 250ms',
          cursor: isAuthenticated ? 'text' : 'pointer',
          opacity: isAuthenticated ? 1 : 0.6,
        }}
        onClick={() => { if (!isAuthenticated) onLoginRequired(); }}
        >
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder={isAuthenticated ? '输入你的问题...' : '登录后开始对话'}
            autoSize={{ minRows: 1, maxRows: 6 }}
            disabled={!isAuthenticated || isStreaming}
            style={{
              border: 'none',
              boxShadow: 'none',
              background: 'transparent',
              resize: 'none',
              fontSize: 15,
              lineHeight: '24px',
              padding: '4px 0',
              flex: 1,
            }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={(e) => {
              if (!isAuthenticated) { e.stopPropagation(); onLoginRequired(); return; }
              handleSend();
            }}
            loading={isStreaming}
            style={{
              height: 40,
              width: 40,
              borderRadius: 12,
              background: (!isAuthenticated || !input.trim()) ? '#d1d5db' : '#4e7dff',
              border: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          />
        </div>

        {/* Quick actions */}
        <div style={{
          display: 'flex', gap: 8, marginTop: 12,
          justifyContent: 'center',
        }}>
          <Button
            type="text"
            icon={<ThunderboltOutlined />}
            onClick={() => { if (!isAuthenticated) { onLoginRequired(); return; } }}
            style={{ color: '#9ca3af', fontSize: 13, borderRadius: 8 }}
          >
            Skill 市场
          </Button>
          <Button
            type="text"
            icon={<ApiOutlined />}
            onClick={() => { if (!isAuthenticated) { onLoginRequired(); return; } }}
            style={{ color: '#9ca3af', fontSize: 13, borderRadius: 8 }}
          >
            接入 MCP
          </Button>
        </div>
      </div>
    </div>
  );
}
