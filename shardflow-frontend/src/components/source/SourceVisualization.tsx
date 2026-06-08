import { Card, Tag, Empty, List, Typography } from 'antd';
import { BookOutlined, GithubOutlined, SearchOutlined, FileTextOutlined, DatabaseOutlined, GlobalOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { useState, useEffect } from 'react';

const { Text } = Typography;

// 数据来源类型映射（企业级规范: 展示数据来源而非工具名称）
const sourceTypeIconMap: Record<string, React.ReactNode> = {
  official_doc: <BookOutlined />,
  stackoverflow: <SearchOutlined />,
  github: <GithubOutlined />,
  web: <GlobalOutlined />,
  knowledge_base: <DatabaseOutlined />,
  file: <FileTextOutlined />,
  code: <FileTextOutlined />,
};

const sourceTypeLabelMap: Record<string, string> = {
  official_doc: '官方文档',
  stackoverflow: '技术社区',
  github: '开源仓库',
  web: '互联网',
  knowledge_base: '知识库',
  file: '文件',
  code: '代码',
};

export default function SourceVisualization() {
  const { messages } = useStore();
  const [sources, setSources] = useState<Array<{ source_type: string; label: string }>>([]);

  useEffect(() => {
    // 企业级规范: 从observe事件中提取数据来源类型，不暴露工具名称和参数
    const dataSources: Array<{ source_type: string; label: string }> = [];
    const seenTypes = new Set<string>();

    for (const msg of messages) {
      if (msg.role === 'assistant' && msg.eventType === 'observe') {
        // observe事件现在只包含success和result，不含工具名
        // 从result内容推断来源类型
        const content = msg.content || '';
        let sourceType = 'web';

        if (content.includes('官方文档') || content.includes('IEEE') || content.includes('标准')) {
          sourceType = 'official_doc';
        } else if (content.includes('stackoverflow') || content.includes('Stack Overflow')) {
          sourceType = 'stackoverflow';
        } else if (content.includes('github') || content.includes('GitHub')) {
          sourceType = 'github';
        } else if (content.includes('知识库') || content.includes('文档库')) {
          sourceType = 'knowledge_base';
        }

        if (!seenTypes.has(sourceType)) {
          seenTypes.add(sourceType);
          dataSources.push({
            source_type: sourceType,
            label: sourceTypeLabelMap[sourceType] || '数据来源',
          });
        }
      }
    }

    setSources(dataSources);
  }, [messages]);

  if (sources.length === 0) {
    return (
      <Card
        title={<span className="cn-title" style={{ letterSpacing: '0.05em', color: 'var(--ink)' }}>数据来源</span>}
        size="small"
        style={{
          background: 'rgba(255,255,255,0.6)',
          border: '1px solid var(--paper-dark)',
        }}
      >
        <Empty description={<span className="cn-tag">推理完成后显示数据来源</span>}>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' }}>
            <Tag icon={<BookOutlined />}>官方文档</Tag>
            <Tag icon={<GlobalOutlined />}>互联网</Tag>
            <Tag icon={<GithubOutlined />}>开源仓库</Tag>
          </div>
        </Empty>
      </Card>
    );
  }

  return (
    <Card
      title={<span className="cn-title" style={{ letterSpacing: '0.05em', color: 'var(--ink)' }}>数据来源</span>}
      size="small"
      style={{
        background: 'rgba(255,255,255,0.6)',
        border: '1px solid var(--paper-dark)',
      }}
    >
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {sources.map((source, idx) => (
          <Tag
            key={idx}
            icon={sourceTypeIconMap[source.source_type] || <DatabaseOutlined />}
            color="default"
          >
            {source.label}
          </Tag>
        ))}
      </div>
    </Card>
  );
}
