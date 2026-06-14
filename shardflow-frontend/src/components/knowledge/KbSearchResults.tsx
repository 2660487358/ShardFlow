import { Card, Tag, Typography, Empty } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';

const { Text, Paragraph } = Typography;

interface SearchResult {
  title?: string;
  filename?: string;
  relevance_score?: number;
  content?: string;
  text?: string;
  document_id?: string;
}

interface Props {
  results: SearchResult[];
  collectionId?: string;
}

export default function KbSearchResults({ results, collectionId }: Props) {
  if (!results || results.length === 0) return null;

  return (
    <div style={{ marginTop: 12, marginBottom: 8 }}>
      <Text type="secondary" style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>
        知识库检索结果（{results.length} 条）
      </Text>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {results.slice(0, 5).map((r, i) => {
          const title = r.title || r.filename || '未知文档';
          const score = r.relevance_score != null ? Math.round(r.relevance_score * 100) : null;
          const snippet = (r.content || r.text || '').slice(0, 200);

          return (
            <Card
              key={i}
              size="small"
              style={{
                background: 'var(--bg-elevated, rgba(255,255,255,0.04))',
                border: '1px solid var(--border-secondary, rgba(255,255,255,0.08))',
                borderRadius: 8,
              }}
              bodyStyle={{ padding: '10px 14px' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <Text strong style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <FileTextOutlined style={{ color: 'var(--accent-warm, #c9a87c)' }} />
                  {title}
                </Text>
                {score != null && (
                  <Tag color={score >= 80 ? 'green' : score >= 65 ? 'orange' : 'default'} style={{ margin: 0, fontSize: 11 }}>
                    {score}%
                  </Tag>
                )}
              </div>
              {snippet && (
                <Paragraph
                  ellipsis={{ rows: 2 }}
                  style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary, rgba(255,255,255,0.55))' }}
                >
                  {snippet}
                </Paragraph>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
