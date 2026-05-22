import { useOutletContext } from 'react-router-dom';
import { useEffect } from 'react';
import { Result, Button } from 'antd';

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function HistoryPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();

  if (!isAuthenticated) {
    return (
      <Result
        icon={<span style={{ fontSize: 48 }}>🔒</span>}
        title="需要登录"
        subTitle="登录后查看历史对话记录"
        extra={<Button type="primary" onClick={onLoginRequired} style={{ background: '#4e7dff' }}>登录</Button>}
      />
    );
  }

  return (
    <div>
      <h2 style={{ fontWeight: 600, color: '#1a1a2e' }}>会话历史</h2>
      <p style={{ color: '#9ca3af' }}>暂无历史对话</p>
    </div>
  );
}
