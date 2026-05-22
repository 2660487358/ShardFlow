import { useOutletContext } from 'react-router-dom';
import { Result, Button } from 'antd';

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function McpToolsPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();

  if (!isAuthenticated) {
    return (
      <Result
        icon={<span style={{ fontSize: 48 }}>🔒</span>}
        title="需要登录"
        subTitle="登录后管理 MCP 工具"
        extra={<Button type="primary" onClick={onLoginRequired} style={{ background: '#4e7dff' }}>登录</Button>}
      />
    );
  }

  return (
    <div>
      <h2 style={{ fontWeight: 600, color: '#1a1a2e' }}>MCP 工具管理</h2>
      <p style={{ color: '#9ca3af' }}>暂无注册工具</p>
    </div>
  );
}
