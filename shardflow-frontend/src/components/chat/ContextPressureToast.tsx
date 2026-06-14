import { Modal, Button, Space, Typography } from 'antd';
import { ExclamationCircleOutlined, WarningOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useStore } from '@/store';

const { Text } = Typography;

const LEVEL_CONFIG = {
  warning: { icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />, color: '#faad14' },
  critical: { icon: <WarningOutlined style={{ color: '#ff7a00' }} />, color: '#ff7a00' },
  full: { icon: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />, color: '#ff4d4f' },
};

export function ContextPressureToast() {
  const pressure = useStore((s) => s.contextPressure);
  const setPressure = useStore((s) => s.setContextPressure);
  const contextSwitchPreview = useStore((s) => s.contextSwitchPreview);

  if (!pressure) return null;

  const config = LEVEL_CONFIG[pressure.level as keyof typeof LEVEL_CONFIG] || LEVEL_CONFIG.warning;
  const isFull = pressure.level === 'full';

  const handleSwitch = async () => {
    const activeTaskId = useStore.getState().activeTaskId;
    const activeSessionId = useStore.getState().activeSessionId;
    const userId = useStore.getState().userId;

    if (!activeTaskId || !activeSessionId) return;

    try {
      const token = localStorage.getItem('shardflow_token');
      const resp = await fetch('/agent/v1/context/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          task_id: activeTaskId,
          session_id: activeSessionId,
          preview_enabled: contextSwitchPreview,
        }),
      });
      if (!resp.ok) throw new Error('Switch failed');
      const data = await resp.json();

      // Navigate to new session
      useStore.getState().clearMessages();
      useStore.getState().setActiveTask(activeTaskId, data.new_session_id);
      setPressure(null);
    } catch (e) {
      console.error('Context switch failed:', e);
    }
  };

  const handleIgnore = () => {
    setPressure(null);
  };

  const handleEndTask = () => {
    // Normal archive flow — just clear for now
    useStore.getState().clearMessages();
    setPressure(null);
  };

  if (isFull) {
    return (
      <Modal
        open
        closable={false}
        maskClosable={false}
        title={<Space>{config.icon}<span>上下文已满</span></Space>}
        footer={[
          <Button key="end" onClick={handleEndTask}>结束任务</Button>,
          <Button key="switch" type="primary" onClick={handleSwitch}>切换上下文</Button>,
        ]}
      >
        <Text>上下文使用率已达 100%，继续对话可能导致输出质量严重下降。</Text>
      </Modal>
    );
  }

  // Toast for warning / critical
  const bgColor = pressure.level === 'critical' ? '#fff7e6' : '#fffbe6';
  const borderColor = pressure.level === 'critical' ? '#ffa940' : '#fadb14';

  return (
    <div style={{
      position: 'fixed', top: 64, left: '50%', transform: 'translateX(-50%)', zIndex: 1050,
      background: bgColor, border: `1px solid ${borderColor}`, borderRadius: 8,
      padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 12,
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    }}>
      {config.icon}
      <Text style={{ color: '#595959' }}>{pressure.message}</Text>
      <Space size={8}>
        <Button size="small" onClick={handleIgnore}>忽略</Button>
        <Button size="small" type="primary" onClick={handleSwitch}>切换上下文</Button>
      </Space>
    </div>
  );
}
