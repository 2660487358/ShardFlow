import { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Spin, Tag, Space, Typography } from 'antd';
import { SendOutlined, LoadingOutlined } from '@ant-design/icons';
import { sendConversation } from '@/api/client';
import { useStore } from '@/store';
import type { ChatMessage, SSEEvent } from '@/types';
import ShardViewer from '@/components/shard/ShardViewer';
import StrategyPanel from '@/components/strategy/StrategyPanel';
import SourceVisualization from '@/components/source/SourceVisualization';

const { TextArea } = Input;
const { Text } = Typography;

const eventColors: Record<string, string> = {
  intent: 'blue', think: 'purple', action: 'orange', observe: 'green',
  shard_trigger: 'red', shard_result: 'magenta', strategy: 'cyan',
  progress: 'geekblue', done: 'green', error: 'red',
};

const eventLabels: Record<string, string> = {
  intent: '意图', think: '思考', action: '工具调用', observe: '观察',
  shard_trigger: '状态包', shard_result: '状态结果', strategy: '策略',
  progress: '进度', done: '完成', error: '错误',
};

export default function ChatPanel() {
  const { messages, addMessage, isStreaming, setStreaming, activeTaskId, activeSessionId, setShard } = useStore();
  const [input, setInput] = useState('');
  const messagesEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || !activeTaskId || isStreaming) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: input, timestamp: Date.now() };
    addMessage(userMsg);
    setInput('');
    setStreaming(true);

    const assistantMsgId = (Date.now() + 1).toString();
    let assistantContent = '';

    await sendConversation(
      activeTaskId,
      userMsg.content,
      activeSessionId || '',
      (event: SSEEvent) => {
        const data = event.data || {};
        assistantContent += formatEventContent(event.type, data);
        // Update the assistant message in-place
        const existing = useStore.getState().messages.find((m) => m.id === assistantMsgId);
        if (existing) {
          useStore.setState({
            messages: useStore.getState().messages.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: assistantContent, eventType: event.type }
                : m
            ),
          });
        } else {
          addMessage({ id: assistantMsgId, role: 'assistant', content: assistantContent, eventType: event.type, timestamp: Date.now() });
        }

        // Handle shard data if present
        if (event.type === 'shard_result' && data.summary) {
          setShard(data as unknown as never);
        }
      },
      (err) => {
        addMessage({ id: (Date.now() + 2).toString(), role: 'system', content: `Error: ${err.message}`, eventType: 'error', timestamp: Date.now() });
        setStreaming(false);
      },
      () => {
        setStreaming(false);
      },
    );
  };

  const formatEventContent = (type: string, data: Record<string, unknown>): string => {
    switch (type) {
      case 'intent': return `**意图**: ${data.intent} (置信度 ${data.confidence})\n\n`;
      case 'think': return `${data.reasoning || ''}`;
      case 'action': return `**🔧 调用工具**: ${data.tool}\n参数: ${JSON.stringify(data.params)}\n\n`;
      case 'observe': return `**结果**: ${data.result}\n\n`;
      case 'done': return `\n\n---\n**✅ 推理完成**\n${data.answer || ''}`;
      case 'error': return `\n\n**❌ 错误**: ${data.message}`;
      default: return '';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: '0 0 16px 0' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#999', paddingTop: 60 }}>
            输入你的问题开始探索代码库
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} style={{ marginBottom: 12 }}>
            {msg.role === 'user' ? (
              <Card size="small" style={{ background: '#e6f4ff', marginLeft: '20%' }}>
                <Text>{msg.content}</Text>
              </Card>
            ) : msg.role === 'system' ? (
              <Card size="small" style={{ background: '#fff2f0' }}>
                <Text type="danger">{msg.content}</Text>
              </Card>
            ) : (
              <Card
                size="small"
                title={
                  msg.eventType ? (
                    <Space>
                      <Tag color={eventColors[msg.eventType] || 'default'}>
                        {eventLabels[msg.eventType] || msg.eventType}
                      </Tag>
                    </Space>
                  ) : null
                }
                style={{ marginRight: '20%' }}
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
              </Card>
            )}
          </div>
        ))}
        {isStreaming && (
          <div style={{ textAlign: 'center', padding: 8 }}>
            <Spin indicator={<LoadingOutlined spin />} /> 推理中...
          </div>
        )}
        <div ref={messagesEnd} />
      </div>

      <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="输入你的问题，例如：理清Dubbo注册链路..."
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={isStreaming}
          />
          <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={isStreaming} style={{ height: 'auto' }}>
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
