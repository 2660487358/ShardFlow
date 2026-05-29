import { Card, List, Tag, Empty, Typography, Button, Space, message } from 'antd';
import { LikeOutlined, DislikeOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import api from '@/api/client';

const { Text } = Typography;

function similarityColor(s: number): string {
  if (s > 0.85) return 'success';
  if (s > 0.70) return 'warning';
  return 'default';
}

function similarityLabel(s: string): string {
  const num = parseFloat(s);
  if (num > 0.85) return '高匹配';
  if (num > 0.70) return '可参考';
  return '低匹配';
}

import type { StrategyRecord } from '@/types';

export default function StrategyPanel() {
  const { strategies } = useStore();

  if (strategies.length === 0) return <Empty description={<span className="cn-tag">暂无策略推荐</span>} />;

  const handleReuse = async (id: string) => {
    try {
      await api.post(`/strategies/${id}/reuse`);
      message.success('策略已应用');
    } catch {
      message.error('应用失败');
    }
  };

  const handleFeedback = async (id: string, fb: string) => {
    try {
      await api.post(`/strategies/${id}/feedback`, { feedback: fb });
      message.success('反馈已提交');
    } catch {
      message.error('反馈失败');
    }
  };

  return (
    <Card
      title={<span className="cn-title" style={{ letterSpacing: '0.05em', color: 'var(--ink)' }}>策略推荐</span>}
      size="small"
      style={{
        background: 'rgba(255,255,255,0.6)',
        border: '1px solid var(--paper-dark)',
      }}
    >
      <List size="small" dataSource={strategies as Array<StrategyRecord & { similarity?: number }>}
        renderItem={(item) => {
          const sim = (item.similarity as number) || 0;
          return (
            <List.Item>
              <div style={{ width: '100%' }}>
                <Space>
                  <Text strong className="cn-sans" style={{ color: 'var(--ink)' }}>{item.task_type as string}</Text>
                  <Tag color={similarityColor(sim)}>{similarityLabel(String(sim))} {(sim * 100).toFixed(0)}%</Tag>
                </Space>
                <br />
                <Text className="cn-tag">{item.query_pattern as string}</Text>
                <br />
                <Space style={{ marginTop: 4 }}>
                  <Button
                    size="small"
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    onClick={() => handleReuse(item.strategy_id as string)}
                    style={{
                      background: 'var(--ink)',
                      border: 'none',
                      fontFamily: 'var(--font-sans)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    应用此策略
                  </Button>
                  <Button
                    size="small"
                    icon={<LikeOutlined />}
                    style={{ borderColor: 'var(--paper-dark)', color: 'var(--ink-soft)' }}
                  />
                  <Button
                    size="small"
                    icon={<DislikeOutlined />}
                    style={{ borderColor: 'var(--paper-dark)', color: 'var(--ink-soft)' }}
                  />
                </Space>
              </div>
            </List.Item>
          );
        }} />
    </Card>
  );
}
