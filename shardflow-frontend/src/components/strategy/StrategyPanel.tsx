import { Card, List, Tag, Empty, Typography } from 'antd';
import { useStore } from '@/store';

const { Text } = Typography;

export default function StrategyPanel() {
  const { strategies } = useStore();

  if (strategies.length === 0) return <Empty description="暂无历史策略" />;

  return (
    <Card title="历史策略" size="small">
      <List size="small" dataSource={strategies}
        renderItem={(item) => (
          <List.Item>
            <div>
              <Text strong>{item.task_type}</Text>
              <br />
              <Text type="secondary">{item.query_pattern}</Text>
              <br />
              <Tag color="blue">成功率 {item.success_score}</Tag>
              <Tag>耗时 {item.cost_ms}ms</Tag>
            </div>
          </List.Item>
        )} />
    </Card>
  );
}
