import { Modal, Switch, Typography, Space } from 'antd';
import { useStore } from '@/store';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function SettingsModal({ open, onClose }: Props) {
  const contextSwitchPreview = useStore((s) => s.contextSwitchPreview);
  const setContextSwitchPreview = useStore((s) => s.setContextSwitchPreview);

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title="设置"
      width={420}
    >
      <div style={{ padding: '8px 0' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text>切换上下文前预览状态包</Text>
          <Switch checked={contextSwitchPreview} onChange={setContextSwitchPreview} />
        </Space>
      </div>
    </Modal>
  );
}
