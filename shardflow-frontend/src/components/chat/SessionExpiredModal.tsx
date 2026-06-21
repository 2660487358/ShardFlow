import { Modal, Button, Typography, Space } from 'antd';
import { ExclamationCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';

const { Text, Title } = Typography;

interface Props {
  open: boolean;
  mode: 'expired' | 'expiring_soon';
  remainingSeconds?: number;
  onNewSession: () => void;
  onClose?: () => void;
}

/**
 * T2.6: Session 过期/即将过期提示弹窗。
 *
 * - expired: 会话已过期，历史记忆已从短期记忆中清除，引导用户新建对话。
 * - expiring_soon: 会话即将过期（5 分钟内），提示用户保存重要结论，可关闭。
 */
export default function SessionExpiredModal({
  open,
  mode,
  remainingSeconds,
  onNewSession,
  onClose,
}: Props) {
  const isExpired = mode === 'expired';

  const remainingMinutes = remainingSeconds
    ? Math.ceil(remainingSeconds / 60)
    : 5;

  return (
    <Modal
      open={open}
      centered
      closable={!isExpired}
      maskClosable={!isExpired}
      keyboard={!isExpired}
      footer={
        isExpired ? (
          <Button type="primary" onClick={onNewSession} style={{ fontFamily: 'var(--font-sans)' }}>
            开启新对话
          </Button>
        ) : (
          <Space>
            <Button onClick={onNewSession} style={{ fontFamily: 'var(--font-sans)' }}>
              立即新建
            </Button>
            <Button type="primary" onClick={onClose} style={{ fontFamily: 'var(--font-sans)' }}>
              稍后
            </Button>
          </Space>
        )
      }
      onCancel={onClose}
      width={420}
    >
      <div style={{ padding: '8px 0', textAlign: 'center' }}>
        {isExpired ? (
          <ExclamationCircleOutlined style={{ fontSize: 48, color: '#faad14', marginBottom: 16 }} />
        ) : (
          <ClockCircleOutlined style={{ fontSize: 48, color: '#c9a87c', marginBottom: 16 }} />
        )}
        <Title level={4} style={{ marginBottom: 8, color: 'var(--ink)' }}>
          {isExpired ? '会话已过期' : '会话即将过期'}
        </Title>
        <Text type="secondary" style={{ display: 'block', lineHeight: 1.7 }}>
          {isExpired
            ? '历史记忆已从短期记忆中清除。是否开启新对话？'
            : `会话将在 ${remainingMinutes} 分钟后过期，建议保存重要结论。`}
        </Text>
      </div>
    </Modal>
  );
}
