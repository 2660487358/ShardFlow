import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Typography } from 'antd';
import { MessageOutlined, UnorderedListOutlined, LogoutOutlined } from '@ant-design/icons';
import { useStore } from '@/store';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token, logout } = useStore();

  if (!token) {
    navigate('/login');
    return null;
  }

  const selectedKey = location.pathname.startsWith('/tasks') ? '/tasks' : '/chat';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} theme="light">
        <div style={{ padding: '16px', fontWeight: 700, fontSize: 16, color: '#1677ff' }}>
          KnowledgeBridge
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          items={[
            { key: '/chat', icon: <MessageOutlined />, label: '对话' },
            { key: '/tasks', icon: <UnorderedListOutlined />, label: '任务' },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Button icon={<LogoutOutlined />} type="text" onClick={logout}>退出</Button>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
