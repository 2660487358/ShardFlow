import { useOutletContext } from 'react-router-dom';
import { Card, Switch, Typography, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useStore } from '@/store';

const { Title, Text } = Typography;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function SettingsPage() {
  const { isAuthenticated } = useOutletContext<OutletContext>();
  const contextSwitchPreview = useStore((s) => s.contextSwitchPreview);
  const setContextSwitchPreview = useStore((s) => s.setContextSwitchPreview);

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用设置功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <SettingOutlined style={{ fontSize: 24, color: 'var(--ink)' }} />
          <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>设置</Title>
        </div>

        <Card
          style={{
            background: 'rgba(255,255,255,0.6)',
            border: '1px solid var(--paper-dark)',
            borderRadius: 12,
          }}
        >
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Text>切换上下文前预览状态包</Text>
            <Switch checked={contextSwitchPreview} onChange={setContextSwitchPreview} />
          </Space>
        </Card>
      </div>
    </div>
  );
}
