import { useState } from 'react';
import { Card, Form, Input, Button, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store';
import { login } from '@/api/client';

const { Title } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const { setAuth } = useStore();
  const navigate = useNavigate();

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const result = await login(values.username, values.password);
      setAuth(result.token, values.username);
      message.success('登录成功');
      navigate('/');
    } catch {
      message.error('用户名或密码错误');
    }
    setLoading(false);
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'var(--paper)', position: 'relative' }}>
      <div className="paper-texture" />
      <Card style={{
        width: 400,
        background: 'rgba(255,255,255,0.6)',
        border: '1px solid var(--paper-dark)',
        borderRadius: 16,
        position: 'relative',
        zIndex: 1,
      }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} className="cn-title" style={{ margin: 0, fontWeight: 600, color: 'var(--ink)', letterSpacing: '0.05em' }}>
            ShardFlow
          </Title>
          <p className="cn-tag" style={{ fontSize: 14, margin: '4px 0 0' }}>个人智能体</p>
        </div>
        <Form onFinish={handleLogin} layout="vertical">
          <Form.Item label={<span className="cn-sans" style={{ color: 'var(--ink-soft)', letterSpacing: '0.04em' }}>用户名</span>} name="username" rules={[{ required: true }]}>
            <Input placeholder="alice" style={{ fontFamily: 'var(--font-sans)', letterSpacing: '0.04em' }} />
          </Form.Item>
          <Form.Item label={<span className="cn-sans" style={{ color: 'var(--ink-soft)', letterSpacing: '0.04em' }}>密码</span>} name="password" rules={[{ required: true }]}>
            <Input.Password placeholder="password" style={{ fontFamily: 'var(--font-sans)' }} />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
              style={{
                height: 44,
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 500,
                background: 'var(--ink)',
                border: 'none',
                boxShadow: '0 4px 12px rgba(42,37,32,0.15)',
                fontFamily: 'var(--font-sans)',
                letterSpacing: '0.08em',
              }}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
