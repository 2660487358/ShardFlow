import { Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AppLayout from './components/layout/AppLayout';
import ChatPage from './pages/ChatPage';
import TaskPage from './pages/TaskPage';
import LoginPage from './pages/LoginPage';

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: { colorPrimary: '#1677ff', borderRadius: 8 },
      }}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<AppLayout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:sessionId" element={<ChatPage />} />
          <Route path="tasks" element={<TaskPage />} />
        </Route>
      </Routes>
    </ConfigProvider>
  );
}
