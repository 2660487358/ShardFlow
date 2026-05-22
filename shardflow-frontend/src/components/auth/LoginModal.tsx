import { useState } from 'react';
import { Modal, Tabs, Form, Input, Button, Typography, message } from 'antd';
import { useStore } from '@/store';
import { login } from '@/api/client';

const { Title } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function LoginModal({ open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState('login');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useStore();
  const [form] = Form.useForm();

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const result = await login(values.username, values.password);
      setAuth(result.token, values.username);
      message.success('登录成功');
      form.resetFields();
      onClose();
    } catch {
      message.error('用户名或密码错误');
    }
    setLoading(false);
  };

  const handleRegister = async (values: { username: string; password: string; confirmPassword: string }) => {
    if (values.password !== values.confirmPassword) {
      message.error('两次密码不一致');
      return;
    }
    setLoading(true);
    try {
      // TODO: replace with register API when available
      message.success('注册成功，已自动登录');
      setAuth('demo-token', values.username);
      form.resetFields();
      onClose();
    } catch {
      message.error('注册失败');
    }
    setLoading(false);
  };

  const tabItems = [
    {
      key: 'login',
      label: '登录',
      children: (
        <Form form={form} onFinish={handleLogin} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
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
                background: '#4e7dff',
                border: 'none',
                boxShadow: '0 1px 3px rgba(78,125,255,0.3)',
              }}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'register',
      label: '注册',
      children: (
        <Form form={form} onFinish={handleRegister} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码', min: 6 }]}>
            <Input.Password placeholder="密码（至少6位）" />
          </Form.Item>
          <Form.Item name="confirmPassword" rules={[{ required: true, message: '请确认密码' }]}>
            <Input.Password placeholder="确认密码" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
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
                background: '#4e7dff',
                border: 'none',
                boxShadow: '0 1px 3px rgba(78,125,255,0.3)',
              }}
            >
              注册
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={400}
      centered
      closable
      styles={{
        body: { padding: '32px 32px 24px' },
        content: { borderRadius: 16, overflow: 'hidden' },
        mask: { background: 'rgba(0,0,0,0.45)' },
      }}
    >
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <Title level={3} style={{ margin: 0, fontWeight: 700, color: '#1a1a2e' }}>
          ShardFlow
        </Title>
        <p style={{ color: '#9ca3af', fontSize: 14, margin: '4px 0 0' }}>
          基于你的画像智能研究，个性化知识获取
        </p>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} centered items={tabItems} />
    </Modal>
  );
}
