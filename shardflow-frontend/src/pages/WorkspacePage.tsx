import { Typography } from 'antd';

const { Title } = Typography;

export default function WorkspacePage() {
  return (
    <div style={{ padding: 32 }}>
      <Title level={4} className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>
        工作区域
      </Title>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />
      <div style={{ color: 'var(--ink-soft)' }}>
        工作区域内容待实现
      </div>
    </div>
  );
}
