import { useState } from 'react';
import { Card, Form, Input, Button, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store';

const { Title } = Typography;

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const { setAuth } = useStore();
  const navigate = useNavigate();

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    // In production: POST /agent/v1/auth/login or Java kb-auth
    // For now, use demo credentials
    if (values.username === 'admin' && values.password === 'admin') {
      setAuth('demo-token', 'default');
      message.success('登录成功');
      navigate('/chat');
    } else {
      message.error('用户名或密码错误');
    }
    setLoading(false);
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f5f5f5' }}>
      <Card style={{ width: 400 }}>
        <Title level={3} style={{ textAlign: 'center' }}>KnowledgeBridge</Title>
        <Form onFinish={handleLogin} layout="vertical">
          <Form.Item label="用户名" name="username" rules={[{ required: true }]}>
            <Input placeholder="admin" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true }]}>
            <Input.Password placeholder="admin" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>登录</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
