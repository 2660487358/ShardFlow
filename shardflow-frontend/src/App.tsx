import { Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from './components/layout/AppLayout';
import ChatPage from './pages/ChatPage';
import LoginPage from './pages/LoginPage';
import HistoryPage from './pages/HistoryPage';
import McpToolsPage from './pages/McpToolsPage';
import ProfilePage from './pages/ProfilePage';
import TaskPage from './pages/TaskPage';
import NotFoundPage from './pages/NotFoundPage';

const fontFamily = "'Noto Serif SC', 'Source Han Serif SC', 'STSong', 'SimSun', 'FangSong', serif";

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#c9a87c',
          borderRadius: 8,
          fontFamily,
          colorBgContainer: '#f7f3ed',
          colorBgLayout: '#f7f3ed',
          colorText: '#2a2520',
          colorTextSecondary: '#5a5348',
          colorBorder: '#e8e2d6',
          colorBorderSecondary: '#e8e2d6',
          colorFill: '#f0ebe2',
          colorFillSecondary: '#f7f3ed',
          colorBgElevated: '#ffffff',
          boxShadow: '0 4px 20px rgba(42,37,32,0.05)',
          fontSize: 14,
          lineHeight: 1.8,
        },
        components: {
          Button: {
            primaryShadow: '0 4px 12px rgba(42,37,32,0.15)',
            defaultColor: '#5a5348',
          },
          Input: {
            activeBorderColor: '#c9a87c',
            hoverBorderColor: '#b8976a',
            colorBgContainer: 'rgba(255,255,255,0.5)',
            activeShadow: '0 0 0 2px rgba(201,168,124,0.1)',
          },
          Card: {
            colorBgContainer: 'rgba(255,255,255,0.6)',
            colorBorderSecondary: '#e8e2d6',
          },
          Modal: {
            contentBg: '#f7f3ed',
            headerBg: '#f7f3ed',
          },
          Tabs: {
            inkBarColor: '#c9a87c',
            itemActiveColor: '#b8976a',
            itemSelectedColor: '#2a2520',
            itemHoverColor: '#5a5348',
          },
          Tag: {
            defaultBg: 'rgba(255,255,255,0.5)',
            defaultColor: '#5a5348',
          },
          Table: {
            colorBgContainer: 'rgba(255,255,255,0.6)',
            headerBg: '#f0ebe2',
            headerColor: '#2a2520',
            rowHoverBg: 'rgba(255,255,255,0.7)',
          },
          Dropdown: {
            colorBgElevated: '#ffffff',
          },
          Progress: {
            colorInfo: '#c9a87c',
            remainingColor: '#e8e2d6',
          },
          Tooltip: {
            colorBgSpotlight: '#2a2520',
          },
          Message: {
            contentBg: '#ffffff',
          },
          Result: {
            colorWhite: '#2a2520',
          },
        },
      }}
    >
      <AntApp>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<AppLayout />}>
            <Route index element={<ChatPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="chat/:sessionId" element={<ChatPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="tasks" element={<TaskPage />} />
            <Route path="mcp-tools" element={<McpToolsPage />} />
            <Route path="profile" element={<ProfilePage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AntApp>
    </ConfigProvider>
  );
}
