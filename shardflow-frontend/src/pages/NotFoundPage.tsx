import { Typography, Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--paper)', position: 'relative' }}>
      <div className="paper-texture" />
      <Result
        status="404"
        title={<span className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>页面不存在</span>}
        subTitle={<span className="cn-tag">你访问的页面不存在或已被移除。</span>}
        extra={
          <Button
            type="primary"
            onClick={() => navigate('/')}
            style={{
              background: 'var(--ink)',
              border: 'none',
              boxShadow: '0 4px 12px rgba(42,37,32,0.15)',
              fontFamily: 'var(--font-sans)',
              letterSpacing: '0.08em',
            }}
          >
            返回首页
          </Button>
        }
      />
    </div>
  );
}
