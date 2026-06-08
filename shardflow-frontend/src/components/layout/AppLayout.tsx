import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button, Dropdown, Avatar, Typography, Tooltip } from 'antd';
import {
  MessageOutlined, HistoryOutlined, UserOutlined,
  LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  ThunderboltOutlined, ApiOutlined,
  PlusOutlined, BookOutlined, ApartmentOutlined,
  SettingOutlined, RobotOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import LoginModal from '@/components/auth/LoginModal';
import CustomModelModal from '@/components/settings/CustomModelModal';
import AgentManageModal from '@/components/settings/AgentManageModal';
import ShardFlowLogo from '@/components/common/ShardFlowLogo';

const { Text } = Typography;

const SIDEBAR_WIDTH = 280;

const mainNavItems = [
  { key: 'chat', icon: <MessageOutlined />, label: '新建会话', path: '/chat' },
];

const featureNavItems = [
  { key: 'skill', icon: <ThunderboltOutlined />, label: 'Skills', path: '/skills' },
  { key: 'mcp', icon: <ApiOutlined />, label: 'MCP', path: '/mcp-tools' },
  { key: 'knowledge', icon: <BookOutlined />, label: '知识库', path: '/kb' },
  { key: 'workspace', icon: <ApartmentOutlined />, label: '记忆图谱', path: '/workspace' },
  { key: 'models', icon: <SettingOutlined />, label: '模型', path: '/models' },
  { key: 'agents', icon: <RobotOutlined />, label: 'Agent', path: '/agents' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token, userId, logout, syncCustomModels, syncAgentConfigs } = useStore();
  const [collapsed, setCollapsed] = useState(false);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [customModelModalOpen, setCustomModelModalOpen] = useState(false);
  const [agentManageModalOpen, setAgentManageModalOpen] = useState(false);

  const isAuthenticated = !!token;

  useEffect(() => {
    if (isAuthenticated) {
      syncCustomModels();
      syncAgentConfigs();
    }
  }, [isAuthenticated, syncCustomModels, syncAgentConfigs]);

  useEffect(() => {
    if (isAuthenticated && location.pathname === '/login') {
      navigate('/');
    }
  }, [isAuthenticated, location.pathname, navigate]);

  // Listen for auth-expired events from the 401 interceptor
  useEffect(() => {
    const handler = () => {
      setLoginModalOpen(true);
    };
    window.addEventListener('shardflow:auth-expired', handler);
    return () => window.removeEventListener('shardflow:auth-expired', handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: '我的画像', onClick: () => navigate('/profile') },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ];

  const isActive = (path: string) => location.pathname.startsWith(path) || (path === '/chat' && location.pathname === '/');

  const handleNavClick = (item: { key: string; path: string }) => {
    if (!isAuthenticated && (item.key === 'skill' || item.key === 'mcp' || item.key === 'agent' || item.key === 'knowledge')) {
      setLoginModalOpen(true);
      return;
    }
    navigate(item.path);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', position: 'relative' }}>
      <div className="paper-texture" />

      {!collapsed && (
        <div
          className="sidebar-mobile-hidden"
          style={{
            width: SIDEBAR_WIDTH,
            background: 'linear-gradient(180deg, var(--paper) 0%, var(--paper-warm) 100%)',
            display: 'flex',
            flexDirection: 'column',
            flexShrink: 0,
            overflow: 'hidden',
            borderRight: '1px solid var(--paper-dark)',
            position: 'relative',
            zIndex: 1,
          }}
        >
          <div style={{
            position: 'absolute',
            top: 0,
            right: -1,
            width: 1,
            height: '100%',
            background: 'linear-gradient(to bottom, transparent 0%, var(--ink-muted) 30%, var(--ink-muted) 70%, transparent 100%)',
            opacity: 0.3,
          }} />

          <div style={{ padding: '24px 24px 16px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
            }}>
              <ShardFlowLogo size={32} />
              <h1 className="cn-title" style={{ fontSize: 20, letterSpacing: '0.08em', color: 'var(--ink)', margin: 0 }}>
                ShardFlow
              </h1>
              <Button
                type="text"
                icon={<MenuFoldOutlined />}
                onClick={() => setCollapsed(true)}
                style={{ color: 'var(--ink-faint)', fontSize: 14, marginLeft: 'auto', padding: '4px 8px' }}
                size="small"
              />
            </div>
          </div>

          <div className="hand-line" style={{ margin: '0 24px' }} />

          <div style={{ padding: '16px 20px' }}>
            {mainNavItems.map((item) => (
              <Tooltip key={item.key} title={item.label} placement="right">
                <div
                  onClick={() => handleNavClick(item)}
                  className="nav-item"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 12px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    color: isActive(item.path) ? 'var(--ink)' : 'var(--ink-faint)',
                    background: isActive(item.path) ? 'rgba(255,255,255,0.5)' : 'transparent',
                    fontWeight: isActive(item.path) ? 500 : 400,
                    fontSize: 14,
                    transition: 'all 0.3s ease',
                    letterSpacing: '0.08em',
                    position: 'relative',
                    marginBottom: 4,
                    border: '1px solid var(--ink)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive(item.path)) {
                      (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.3)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-soft)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive(item.path)) {
                      (e.currentTarget as HTMLElement).style.background = 'transparent';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-faint)';
                    }
                  }}
                >
                  <span style={{ fontSize: 16 }}>{item.icon}</span>
                  <span>{item.label}</span>
                </div>
              </Tooltip>
            ))}
          </div>

          <div style={{ padding: '4px 20px 16px' }}>
            {featureNavItems.map((item) => (
              <Tooltip
                key={item.key}
                title={isAuthenticated ? item.label : '登录后可用'}
                placement="right"
              >
                <div
                  onClick={() => handleNavClick(item)}
                  className="nav-item"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 12px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    color: isActive(item.path) ? 'var(--ink)' : 'var(--ink-faint)',
                    background: isActive(item.path) ? 'rgba(255,255,255,0.5)' : 'transparent',
                    fontWeight: isActive(item.path) ? 500 : 400,
                    transition: 'all 0.3s ease',
                    fontSize: 14,
                    letterSpacing: '0.08em',
                    position: 'relative',
                    marginBottom: 4,
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive(item.path)) {
                      (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.3)';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-soft)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive(item.path)) {
                      (e.currentTarget as HTMLElement).style.background = 'transparent';
                      (e.currentTarget as HTMLElement).style.color = 'var(--ink-faint)';
                    }
                  }}
                >
                  <span style={{ fontSize: 16 }}>{item.icon}</span>
                  <span>{item.label}</span>
                </div>
              </Tooltip>
            ))}

          </div>

          <div className="hand-line" style={{ margin: '0 24px' }} />

          <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
            <div className="cn-sans" style={{
              padding: '8px 8px 4px',
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--ink-faint)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              letterSpacing: '0.1em',
            }}>
              历史会话
              <HistoryOutlined style={{ fontSize: 12 }} />
            </div>
            {!isAuthenticated && (
              <div style={{ padding: '16px 12px', textAlign: 'center' }}>
                <Text className="cn-tag" style={{ fontSize: 13, color: 'var(--ink-muted)' }}>登录后可查看历史对话</Text>
              </div>
            )}
          </div>

          <div style={{
            padding: '16px 20px',
            borderTop: '1px solid var(--paper-dark)',
            display: 'flex',
            alignItems: 'center',
          }}>
            {isAuthenticated ? (
              <Dropdown menu={{ items: userMenuItems }} placement="topRight" trigger={['click']}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  cursor: 'pointer',
                  padding: '6px 10px',
                  borderRadius: 8,
                  width: '100%',
                  transition: 'background 0.3s ease',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.4)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                >
                  <div style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    border: '2px solid var(--ink-muted)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--ink)',
                    fontSize: 14,
                    fontWeight: 500,
                    flexShrink: 0,
                  }} className="cn-sans">
                    {(userId || '用')[0]}
                  </div>
                  <div>
                    <Text className="cn-sans" style={{ color: 'var(--ink)', fontSize: 14, fontWeight: 500, letterSpacing: '0.04em' }}>{userId || '用户'}</Text>
                    <p className="cn-tag" style={{ fontSize: 11, margin: 0 }}>专业版会员</p>
                  </div>
                </div>
              </Dropdown>
            ) : (
              <div
                onClick={() => setLoginModalOpen(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  cursor: 'pointer',
                  padding: '6px 10px',
                  borderRadius: 8,
                  width: '100%',
                  color: 'var(--ink-faint)',
                  fontSize: 14,
                  transition: 'background 0.3s ease',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.4)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
              >
                <div style={{
                  width: 30,
                  height: 30,
                  borderRadius: '50%',
                  border: '2px solid var(--ink-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <UserOutlined style={{ fontSize: 14, color: 'var(--ink-faint)' }} />
                </div>
                <span className="cn-sans">登录后获得更多功能</span>
              </div>
            )}
          </div>
        </div>
      )}

      {collapsed && (
        <div
          className="sidebar-mobile-hidden"
          style={{
            width: 48,
            background: 'linear-gradient(180deg, var(--paper) 0%, var(--paper-warm) 100%)',
            borderRight: '1px solid var(--paper-dark)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingTop: 16,
            flexShrink: 0,
            zIndex: 1,
          }}
        >
          <Button
            type="text"
            icon={<MenuUnfoldOutlined />}
            onClick={() => setCollapsed(false)}
            style={{ color: 'var(--ink-faint)', fontSize: 16 }}
          />
        </div>
      )}

      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--paper)',
        overflow: 'hidden',
        position: 'relative',
        zIndex: 1,
      }}>
        <Outlet context={{ onLoginRequired: () => setLoginModalOpen(true), isAuthenticated }} />
      </div>

      <LoginModal open={loginModalOpen} onClose={() => setLoginModalOpen(false)} />
      <CustomModelModal open={customModelModalOpen} onClose={() => setCustomModelModalOpen(false)} />
      <AgentManageModal open={agentManageModalOpen} onClose={() => setAgentManageModalOpen(false)} />
    </div>
  );
}
