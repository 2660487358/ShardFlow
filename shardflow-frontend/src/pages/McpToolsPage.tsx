import { useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Result, Button, Card, Tag, List, Typography, Badge, Skeleton, message, Empty, Spin } from 'antd';
import { ToolOutlined, ApiOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchMcpTools } from '@/api/client';

const { Title, Text, Paragraph } = Typography;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

interface McpTool {
  tool_id: string;
  tool_name: string;
  description: string;
  version: string;
  status: string;
  last_health_check?: string;
}

export default function McpToolsPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const { mcpTools, mcpLoading, setMcpTools, setMcpLoading } = useStore();

  useEffect(() => {
    if (!isAuthenticated) return;
    setMcpLoading(true);
    fetchMcpTools()
      .then((data) => {
        const tools = Array.isArray(data) ? data : (data as Record<string, unknown>)?.tools || [];
        setMcpTools(tools as McpTool[]);
      })
      .catch(() => { message.error('获取工具列表失败'); })
      .finally(() => { setMcpLoading(false); });
  }, [isAuthenticated, setMcpTools, setMcpLoading]);

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用 MCP 管理功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>MCP</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理已注册的 MCP 工具，查看工具状态和版本信息</Text>
          </div>
        </div>

        {/* MCP 工具列表 */}
        {mcpLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
        ) : mcpTools.length === 0 ? (
          <Empty description="还没有注册的 MCP 工具" />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {mcpTools.map((tool: McpTool) => {
              const isOnline = tool.status === 'ONLINE' || tool.status === 'active';
              return (
                <Card
                  key={tool.tool_id}
                  hoverable
                  style={{
                    borderColor: isOnline ? 'var(--accent)' : undefined,
                  }}
                >
                  <Card.Meta
                    avatar={
                      <div style={{
                        width: 40, height: 40, borderRadius: 10,
                        background: isOnline ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: isOnline ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                      }}>
                        <ApiOutlined style={{ fontSize: 20, color: isOnline ? 'var(--accent-warm)' : '#c9a87c' }} />
                      </div>
                    }
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span>{tool.tool_name}</span>
                        <Tag>v{tool.version}</Tag>
                        <Tag color={isOnline ? 'success' : 'default'} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                          {isOnline ? '在线' : '离线'}
                        </Tag>
                      </div>
                    }
                    description={
                      <>
                        <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                          {tool.description || '暂无描述'}
                        </Paragraph>
                        <div style={{ display: 'flex', gap: 16 }}>
                          {tool.last_health_check && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              上次检查: {tool.last_health_check}
                            </Text>
                          )}
                        </div>
                      </>
                    }
                  />
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
