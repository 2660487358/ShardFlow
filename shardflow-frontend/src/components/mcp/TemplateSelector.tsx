import { useState, useEffect } from 'react';
import { Input, Select, Card, Row, Col, Tag, Empty, Spin, Typography, Space } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { McpTemplate } from '@/types';
import { fetchMcpTemplates } from '@/api/client';

const { Title, Text, Paragraph } = Typography;

interface TemplateSelectorProps {
  onSelect: (template: McpTemplate) => void;
  selectedTemplateId?: string;
}

const CATEGORY_OPTIONS = [
  { value: '', label: '全部分类' },
  { value: 'office', label: '办公协作' },
  { value: 'code', label: '代码开发' },
  { value: 'data', label: '数据平台' },
  { value: 'search', label: '搜索知识' },
  { value: 'file', label: '文件操作' },
  { value: 'database', label: '数据库' },
  { value: 'project', label: '项目管理' },
];

function transportTag(transport: string) {
  const map: Record<string, { color: string; label: string }> = {
    'stdio': { color: 'blue', label: 'stdio' },
    'http-sse': { color: 'green', label: 'SSE' },
    'cloud': { color: 'purple', label: 'Cloud' },
  };
  const info = map[transport] || { color: 'default', label: transport };
  return <Tag color={info.color}>{info.label}</Tag>;
}

export default function TemplateSelector({ onSelect, selectedTemplateId }: TemplateSelectorProps) {
  const [templates, setTemplates] = useState<McpTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [category, setCategory] = useState('');
  const [displayTemplates, setDisplayTemplates] = useState<McpTemplate[]>([]);

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    filterTemplates();
  }, [keyword, category, templates]);

  async function loadTemplates() {
    setLoading(true);
    try {
      const result = await fetchMcpTemplates();
      setTemplates(result.templates || []);
    } catch (error) {
      console.error('Failed to load templates:', error);
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }

  function filterTemplates() {
    let filtered = templates;

    if (category) {
      filtered = filtered.filter(t => t.category === category);
    }

    if (keyword) {
      const lowerKeyword = keyword.toLowerCase();
      filtered = filtered.filter(t =>
        t.displayName.toLowerCase().includes(lowerKeyword) ||
        t.description.toLowerCase().includes(lowerKeyword) ||
        (t.tags && t.tags.some(tag => tag.toLowerCase().includes(lowerKeyword)))
      );
    }

    setDisplayTemplates(filtered);
  }

  return (
    <div>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Row gutter={16}>
          <Col span={16}>
            <Input
              placeholder="搜索模板名称、描述或标签"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              allowClear
            />
          </Col>
          <Col span={8}>
            <Select
              style={{ width: '100%' }}
              placeholder="选择分类"
              value={category}
              onChange={(value) => setCategory(value)}
              options={CATEGORY_OPTIONS}
            />
          </Col>
        </Row>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
          </div>
        ) : displayTemplates.length === 0 ? (
          <Empty description="没有找到匹配的模板" />
        ) : (
          <Row gutter={[16, 16]}>
            {displayTemplates.map((template) => (
              <Col key={template.templateId} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  onClick={() => onSelect(template)}
                  style={{
                    border: selectedTemplateId === template.templateId ? '2px solid #1890ff' : undefined,
                    height: '100%',
                  }}
                >
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    <div>
                      {template.iconUrl && (
                        <img
                          src={template.iconUrl}
                          alt={template.displayName}
                          style={{ width: 32, height: 32, marginRight: 8, verticalAlign: 'middle' }}
                        />
                      )}
                      <Text strong style={{ fontSize: 16 }}>
                        {template.displayName}
                      </Text>
                    </div>
                    <Paragraph
                      ellipsis={{ rows: 2 }}
                      style={{ marginBottom: 8, color: '#666' }}
                    >
                      {template.description}
                    </Paragraph>
                    <Space size="small">
                      {transportTag(template.transport)}
                      {template.tags && template.tags.slice(0, 2).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}

        <Text type="secondary" style={{ textAlign: 'center', display: 'block' }}>
          共 {templates.length} 个模板，当前显示 {displayTemplates.length} 个
        </Text>
      </Space>
    </div>
  );
}
