import { Card, List, Tag, Empty, Typography, Button, Space, message } from 'antd';
import { LikeOutlined, DislikeOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import api from '@/api/client';

const { Text } = Typography;

function similarityColor(s: number): string {
  if (s > 0.85) return 'green';
  if (s > 0.70) return 'gold';
  return 'default';
}

function similarityLabel(s: number): string {
  if (s > 0.85) return '高匹配';
  if (s > 0.70) return '可参考';
  return '低匹配';
}

import type { StrategyRecord } from '@/types';

// ... keep existing imports

export default function StrategyPanel() {
  const { strategies } = useStore();

  if (strategies.length === 0) return <Empty description="暂无策略推荐" />;

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
    <Card title="策略推荐" size="small">
      <List size="small" dataSource={strategies as Array<StrategyRecord & { similarity?: number }>}
        renderItem={(item) => {
          const sim = (item.similarity as number) || 0;
          return (
            <List.Item>
              <div style={{ width: '100%' }}>
                <Space>
                  <Text strong>{item.task_type as string}</Text>
                  <Tag color={similarityColor(sim)}>{similarityLabel(sim)} {(sim * 100).toFixed(0)}%</Tag>
                </Space>
                <br />
                <Text type="secondary">{item.query_pattern as string}</Text>
                <br />
                <Space style={{ marginTop: 4 }}>
                  <Button size="small" type="primary" icon={<ThunderboltOutlined />}
                    onClick={() => handleReuse(item.strategy_id as string)}>
                    应用此策略
                  </Button>
                  <Button size="small" icon={<LikeOutlined />}
                    onClick={() => handleFeedback(item.strategy_id as string, 'like')} />
                  <Button size="small" icon={<DislikeOutlined />}
                    onClick={() => handleFeedback(item.strategy_id as string, 'dislike')} />
                </Space>
              </div>
            </List.Item>
          );
        }} />
    </Card>
  );
}
