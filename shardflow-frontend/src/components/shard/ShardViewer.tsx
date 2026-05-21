import { Card, Descriptions, Tag, List, Empty, Typography } from 'antd';
import type { ShardData } from '@/types';
import { useStore } from '@/store';

const { Text } = Typography;

export default function ShardViewer() {
  const { currentShard } = useStore();
  if (!currentShard) return <Empty description="暂无状态包数据" />;

  const shard = currentShard as ShardData;

  return (
    <Card title="当前状态包" size="small">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="深度">{shard.exploration_depth}</Descriptions.Item>
        <Descriptions.Item label="版本">{shard.version}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={shard.status === 'SHARDED' ? 'blue' : 'default'}>{shard.status}</Tag>
        </Descriptions.Item>
      </Descriptions>

      <Text strong>已确认知识点</Text>
      <List size="small" dataSource={shard.confirmed || []}
        renderItem={(item: { fact: string; confidence: number }) => (
          <List.Item><Text>{item.fact}</Text> <Tag>{item.confidence}</Tag></List.Item>
        )} />

      <Text strong>已排除假设</Text>
      <List size="small" dataSource={shard.excluded || []}
        renderItem={(item: { hypothesis: string; reason: string }) => (
          <List.Item><Text delete>{item.hypothesis}</Text> — {item.reason}</List.Item>
        )} />

      <Text strong>待探索</Text>
      <List size="small" dataSource={shard.pending || []}
        renderItem={(item: string) => <List.Item>{item}</List.Item>} />
    </Card>
  );
}
