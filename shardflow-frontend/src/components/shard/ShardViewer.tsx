import { Card, Tabs, List, Tag, Empty, Typography, Progress, Space } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ToolOutlined } from '@ant-design/icons';
import type { ContextShard } from '@/types';
import { useStore } from '@/store';

const { Text } = Typography;

export default function ShardViewer() {
  const { currentShard } = useStore();

  if (!currentShard) return <Empty description="尚未提取 ContextShard" className="cn-tag" />;

  const shard: ContextShard = currentShard;

  const ks = shard.knowledge_state || { confirmed: [], excluded: [], pending: [], key_decisions: [] };
  const uc = shard.user_context || { expertise_level: '', preferred_depth: '', communication_style: '' };
  const es = shard.execution_state || { progress: 0, completed_steps: [], tools_used: [] };
  const sp = shard.source_preference || {};

  const tabItems = [
    {
      key: 'knowledge',
      label: <span className="cn-sans">知识状态</span>,
      children: (
        <div>
          <Text strong className="cn-sans" style={{ color: 'var(--ink)' }}>已确认 ({ks.confirmed.length})</Text>
          <List size="small" dataSource={ks.confirmed}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: { fact: string; confidence: number }) => (
              <List.Item>
                <Space>
                  <CheckCircleOutlined style={{ color: 'var(--accent-warm)' }} />
                  <Text className="cn-body" style={{ color: 'var(--ink-soft)' }}>{item.fact}</Text>
                  <Progress percent={Math.round((item.confidence || 0) * 100)} size="small" style={{ width: 80 }} />
                </Space>
              </List.Item>
            )} />
          <Text strong className="cn-sans" style={{ marginTop: 8, display: 'block', color: 'var(--ink)' }}>已排除 ({ks.excluded.length})</Text>
          <List size="small" dataSource={ks.excluded}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: { hypothesis: string; reason: string }) => (
              <List.Item>
                <Space>
                  <CloseCircleOutlined style={{ color: '#b85c5c' }} />
                  <Text delete className="cn-body" style={{ color: 'var(--ink-soft)' }}>{item.hypothesis}</Text>
                  <Text type="secondary" className="cn-tag">— {item.reason}</Text>
                </Space>
              </List.Item>
            )} />
          <Text strong className="cn-sans" style={{ marginTop: 8, display: 'block', color: 'var(--ink)' }}>待探索 ({ks.pending.length})</Text>
          <List size="small" dataSource={ks.pending}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: string) => (
              <List.Item><ClockCircleOutlined style={{ color: 'var(--accent)' }} /> <Text className="cn-body" style={{ color: 'var(--ink-soft)' }}>{item}</Text></List.Item>
            )} />
        </div>
      ),
    },
    {
      key: 'user',
      label: <span className="cn-sans">用户上下文</span>,
      children: (
        <div>
          <p><Text strong className="cn-sans" style={{ color: 'var(--ink)' }}>专业水平：</Text><Tag>{uc.expertise_level || '未知'}</Tag></p>
          <p><Text strong className="cn-sans" style={{ color: 'var(--ink)' }}>探索深度：</Text><Tag color="default">{uc.preferred_depth || '默认'}</Tag></p>
          <p><Text strong className="cn-sans" style={{ color: 'var(--ink)' }}>沟通风格：</Text><Tag color="default">{uc.communication_style || '默认'}</Tag></p>
        </div>
      ),
    },
    {
      key: 'execution',
      label: <span className="cn-sans">执行状态</span>,
      children: (
        <div>
          <Progress percent={Math.round((es.progress || 0) * 100)} />
          <Text strong className="cn-sans" style={{ marginTop: 8, display: 'block', color: 'var(--ink)' }}>已完成步骤：</Text>
          <List size="small" dataSource={es.completed_steps || []}
            locale={{ emptyText: '暂无' }}
            renderItem={(step: string) => <List.Item><CheckCircleOutlined style={{ color: 'var(--accent-warm)' }} /> <Text className="cn-body" style={{ color: 'var(--ink-soft)' }}>{step}</Text></List.Item>} />
          <Text strong className="cn-sans" style={{ marginTop: 8, display: 'block', color: 'var(--ink)' }}>使用工具：</Text>
          <Space>{((es.tools_used || []) as string[]).map((t: string) => <Tag icon={<ToolOutlined />} key={t}>{t}</Tag>)}</Space>
        </div>
      ),
    },
    {
      key: 'source',
      label: <span className="cn-sans">来源偏好</span>,
      children: (
        <div>
          {Object.keys(sp).length === 0 ? <Text className="cn-tag">暂无来源偏好</Text> :
            Object.entries(sp).map(([key, val]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <Text className="cn-sans" style={{ color: 'var(--ink-soft)' }}>{key}</Text>
                <Progress percent={Math.round((val as number) * 100)} size="small" />
              </div>
            ))
          }
        </div>
      ),
    },
  ];

  return (
    <Card
      title={<span className="cn-title" style={{ letterSpacing: '0.05em', color: 'var(--ink)' }}>ContextShard</span>}
      size="small"
      style={{
        background: 'rgba(255,255,255,0.6)',
        border: '1px solid var(--paper-dark)',
      }}
    >
      <Tabs items={tabItems} size="small" />
    </Card>
  );
}
