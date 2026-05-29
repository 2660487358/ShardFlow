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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Result
          icon={<span style={{ fontSize: 48, opacity: 0.6 }}>🔧</span>}
          title={<span className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>需要登录</span>}
          subTitle={<span className="cn-tag">登录后管理 MCP 工具</span>}
          extra={
            <Button
              type="primary"
              onClick={onLoginRequired}
              style={{
                background: 'var(--ink)',
                border: 'none',
                boxShadow: '0 4px 12px rgba(42,37,32,0.15)',
                fontFamily: 'var(--font-sans)',
                letterSpacing: '0.08em',
              }}
            >
              登录
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 32 }}>
      <h2 className="cn-title" style={{ fontWeight: 600, color: 'var(--ink)', letterSpacing: '0.05em' }}>MCP 工具管理</h2>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />
      <p className="cn-tag">暂无注册工具</p>
    </div>
  );
}
