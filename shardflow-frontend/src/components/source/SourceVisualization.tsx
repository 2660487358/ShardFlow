import { Card, Tag, Empty, List, Typography } from 'antd';
import { CodeOutlined, BookOutlined, GithubOutlined, SearchOutlined, FileTextOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { useState, useEffect } from 'react';

const { Text } = Typography;

const sourceIconMap: Record<string, React.ReactNode> = {
  search_code: <SearchOutlined />,
  read_file: <FileTextOutlined />,
  query_source: <DatabaseOutlined />,
  code_comments: <CodeOutlined />,
  official_docs: <BookOutlined />,
  github: <GithubOutlined />,
};

const sourceColorMap: Record<string, string> = {
  search_code: 'blue',
  read_file: 'geekblue',
  query_source: 'purple',
  code_comments: 'blue',
  official_docs: 'green',
  github: 'orange',
};

export default function SourceVisualization() {
  const { messages } = useStore();
  const [sources, setSources] = useState<Array<{ tool: string; params: Record<string, unknown> }>>([]);

  useEffect(() => {
    const actionSources: Array<{ tool: string; params: Record<string, unknown> }> = [];
    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.eventType === 'action') {
        const content = msg.content;
        const toolMatch = content.match(/调用工具\*\*:\s*(\S+)/);
        const paramsMatch = content.match(/参数:\s*({.*})/);
        if (toolMatch) {
          let params: Record<string, unknown> = {};
          if (paramsMatch) {
            try { params = JSON.parse(paramsMatch[1]); } catch { /* ignore */ }
          }
          actionSources.push({ tool: toolMatch[1], params });
        }
      }
    }
    setSources(actionSources);
  }, [messages]);

  if (sources.length === 0) {
    return (
      <Card title="信息来源" size="small">
        <Empty description="推理完成后显示多路召回来源">
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
            <Tag icon={<CodeOutlined />} color="blue">代码注释</Tag>
            <Tag icon={<BookOutlined />} color="green">官方文档</Tag>
            <Tag icon={<GithubOutlined />} color="orange">GitHub</Tag>
          </div>
        </Empty>
      </Card>
    );
  }

  return (
    <Card title="信息来源" size="small">
      <List size="small" dataSource={sources}
        renderItem={(item) => (
          <List.Item>
            <Tag icon={sourceIconMap[item.tool] || <CodeOutlined />} color={sourceColorMap[item.tool] || 'default'}>
              {item.tool}
            </Tag>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {String(item.params.query || item.params.path || item.params.source_type || JSON.stringify(item.params))}
            </Text>
          </List.Item>
        )} />
    </Card>
  );
}
