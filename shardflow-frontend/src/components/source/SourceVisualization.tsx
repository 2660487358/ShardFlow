import { Card, Tag, Empty } from 'antd';
import { GithubOutlined, BookOutlined, CodeOutlined } from '@ant-design/icons';

export default function SourceVisualization() {
  // In production, sources come from SSE events
  return (
    <Card title="信息来源" size="small">
      <Empty description="推理完成后显示多路召回来源">
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 8 }}>
          <Tag icon={<CodeOutlined />} color="blue">代码注释</Tag>
          <Tag icon={<BookOutlined />} color="green">官方文档</Tag>
          <Tag icon={<GithubOutlined />} color="orange">GitHub</Tag>
        </div>
      </Empty>
    </Card>
  );
}
