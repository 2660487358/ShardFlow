import { Card, Tabs, List, Tag, Empty, Typography, Progress, Space } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ToolOutlined } from '@ant-design/icons';
import type { ContextShard, ShardData } from '@/types';
import { useStore } from '@/store';

const { Text } = Typography;

export default function ShardViewer() {
  const { currentShard } = useStore();

  if (!currentShard) return <Empty description="尚未提取 ContextShard" />;

  const shard = currentShard as ContextShard & ShardData;

  const ks = shard.knowledge_state || { confirmed: shard.confirmed || [], excluded: shard.excluded || [], pending: shard.pending || [], key_decisions: shard.key_decisions || [] };
  const uc = shard.user_context || { expertise_level: '', preferred_depth: '', communication_style: '' };
  const es = shard.execution_state || { progress: 0, completed_steps: [], tools_used: [] };
  const sp = shard.source_preference || {};

  const tabItems = [
    {
      key: 'knowledge',
      label: '知识状态',
      children: (
        <div>
          <Text strong>已确认 ({ks.confirmed.length})</Text>
          <List size="small" dataSource={ks.confirmed}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: { fact: string; confidence: number }) => (
              <List.Item>
                <Space>
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                  <Text>{item.fact}</Text>
                  <Progress percent={Math.round((item.confidence || 0) * 100)} size="small" style={{ width: 80 }} />
                </Space>
              </List.Item>
            )} />
          <Text strong style={{ marginTop: 8, display: 'block' }}>已排除 ({ks.excluded.length})</Text>
          <List size="small" dataSource={ks.excluded}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: { hypothesis: string; reason: string }) => (
              <List.Item>
                <Space>
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                  <Text delete>{item.hypothesis}</Text>
                  <Text type="secondary">— {item.reason}</Text>
                </Space>
              </List.Item>
            )} />
          <Text strong style={{ marginTop: 8, display: 'block' }}>待探索 ({ks.pending.length})</Text>
          <List size="small" dataSource={ks.pending}
            locale={{ emptyText: '暂无' }}
            renderItem={(item: string) => (
              <List.Item><ClockCircleOutlined style={{ color: '#faad14' }} /> <Text>{item}</Text></List.Item>
            )} />
        </div>
      ),
    },
    {
      key: 'user',
      label: '用户上下文',
      children: (
        <div>
          <p><Text strong>专业水平：</Text><Tag>{uc.expertise_level || '未知'}</Tag></p>
          <p><Text strong>探索深度：</Text><Tag color="blue">{uc.preferred_depth || '默认'}</Tag></p>
          <p><Text strong>沟通风格：</Text><Tag color="purple">{uc.communication_style || '默认'}</Tag></p>
        </div>
      ),
    },
    {
      key: 'execution',
      label: '执行状态',
      children: (
        <div>
          <Progress percent={Math.round((es.progress || 0) * 100)} />
          <Text strong style={{ marginTop: 8, display: 'block' }}>已完成步骤：</Text>
          <List size="small" dataSource={es.completed_steps || []}
            locale={{ emptyText: '暂无' }}
            renderItem={(step: string) => <List.Item><CheckCircleOutlined style={{ color: '#52c41a' }} /> {step}</List.Item>} />
          <Text strong style={{ marginTop: 8, display: 'block' }}>使用工具：</Text>
          <Space>{((es.tools_used || []) as string[]).map((t: string) => <Tag icon={<ToolOutlined />} key={t}>{t}</Tag>)}</Space>
        </div>
      ),
    },
    {
      key: 'source',
      label: '来源偏好',
      children: (
        <div>
          {Object.keys(sp).length === 0 ? <Text type="secondary">暂无来源偏好</Text> :
            Object.entries(sp).map(([key, val]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <Text>{key}</Text>
                <Progress percent={Math.round((val as number) * 100)} size="small" />
              </div>
            ))
          }
        </div>
      ),
    },
  ];

  return (
    <Card title="ContextShard" size="small">
      <Tabs items={tabItems} size="small" />
    </Card>
  );
}
