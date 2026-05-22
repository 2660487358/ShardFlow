import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button, Dropdown, Avatar, Typography, Tooltip } from 'antd';
import {
  MessageOutlined, HistoryOutlined, ToolOutlined, UserOutlined,
  LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  ThunderboltOutlined, ApiOutlined, LoginOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import LoginModal from '@/components/auth/LoginModal';

const { Text } = Typography;

const SIDEBAR_WIDTH = 280;
const SIDEBAR_COLLAPSED_WIDTH = 64;

const toolItems = [
  { key: 'skill', icon: <ThunderboltOutlined />, label: 'Skill 市场' },
  { key: 'mcp', icon: <ApiOutlined />, label: '接入 MCP' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token, userId, logout } = useStore();
  const [collapsed, setCollapsed] = useState(false);
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  const isAuthenticated = !!token;

  useEffect(() => {
    if (isAuthenticated && location.pathname === '/login') {
      navigate('/');
    }
  }, [isAuthenticated, location.pathname, navigate]);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: '我的画像', onClick: () => navigate('/profile') },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ];

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* ============ Sidebar ============ */}
      <div style={{
        width: collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH,
        background: '#16162a',
        display: 'flex',
        flexDirection: 'column',
        transition: `width 250ms cubic-bezier(0.4, 0, 0.2, 1)`,
        flexShrink: 0,
        overflow: 'hidden',
      }}>
        {/* Logo */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
          padding: collapsed ? '16px 0' : '16px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}>
          {!collapsed && (
            <span style={{ fontWeight: 700, fontSize: 18, color: '#f0f0f5', whiteSpace: 'nowrap' }}>
              ShardFlow
            </span>
          )}
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{ color: '#9ca3af', fontSize: 16 }}
          />
        </div>

        {/* Tools */}
        <div style={{ padding: collapsed ? '12px 0' : '12px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          {toolItems.map((item) => (
            <Tooltip key={item.key} title={isAuthenticated ? item.label : '登录后可用'} placement="right">
              <div
                onClick={() => {
                  if (!isAuthenticated) { setLoginModalOpen(true); return; }
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: collapsed ? 0 : 12,
                  padding: collapsed ? '12px 0' : '10px 12px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  color: isAuthenticated ? '#9ca3af' : '#6b7280',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  transition: 'background 150ms',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#1e1e3a'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
              >
                <span style={{ fontSize: 18, opacity: isAuthenticated ? 1 : 0.4 }}>{item.icon}</span>
                {!collapsed && (
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, color: isAuthenticated ? '#f0f0f5' : '#6b7280' }}>
                      {item.label}
                    </div>
                  </div>
                )}
                {!collapsed && !isAuthenticated && <span style={{ fontSize: 14 }}>🔒</span>}
              </div>
            </Tooltip>
          ))}
        </div>

        {/* History */}
        <div style={{ flex: 1, overflow: 'auto', padding: collapsed ? '8px 0' : '8px 12px' }}>
          {!collapsed && (
            <div
              style={{
                padding: '8px 12px',
                fontSize: 12,
                fontWeight: 600,
                color: '#6b7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              历史对话
            </div>
          )}
          {!collapsed && !isAuthenticated && (
            <div style={{ padding: '16px 12px', textAlign: 'center' }}>
              <Text style={{ fontSize: 13, color: '#6b7280' }}>登录后可查看历史对话</Text>
            </div>
          )}
          {collapsed && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0' }}>
              <HistoryOutlined style={{ color: '#6b7280', fontSize: 18 }} />
            </div>
          )}
        </div>

        {/* User */}
        <div style={{
          padding: collapsed ? '12px 0' : '12px 16px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}>
          {isAuthenticated ? (
            <Dropdown menu={{ items: userMenuItems }} placement="topRight" trigger={['click']}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: collapsed ? 0 : 10,
                cursor: 'pointer',
                padding: collapsed ? '8px' : '8px 12px',
                borderRadius: 8,
                width: collapsed ? 'auto' : '100%',
                justifyContent: collapsed ? 'center' : 'flex-start',
              }}>
                <Avatar size={32} icon={<UserOutlined />} style={{ background: '#4e7dff', flexShrink: 0 }} />
                {!collapsed && <Text style={{ color: '#f0f0f5', fontSize: 14, fontWeight: 500 }}>{userId}</Text>}
              </div>
            </Dropdown>
          ) : (
            <Button
              type="primary"
              icon={<LoginOutlined />}
              onClick={() => setLoginModalOpen(true)}
              style={{
                background: '#4e7dff',
                border: 'none',
                borderRadius: 8,
                fontWeight: 500,
                width: collapsed ? 'auto' : '100%',
              }}
            >
              {!collapsed && '登录'}
            </Button>
          )}
        </div>
      </div>

      {/* ============ Main ============ */}
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        background: '#f7f7f8',
        overflow: 'hidden',
      }}>
        <Outlet context={{ onLoginRequired: () => setLoginModalOpen(true), isAuthenticated }} />
      </div>

      {/* Login Modal */}
      <LoginModal open={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
    </div>
  );
}
