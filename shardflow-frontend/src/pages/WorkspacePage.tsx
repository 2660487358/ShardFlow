import { Empty, Typography } from 'antd';
import { useStore } from '@/store';
import SourceVisualization from '@/components/source/SourceVisualization';

const { Title } = Typography;

export default function WorkspacePage() {
  const { activeTaskId } = useStore();
  const hasActiveWork = !!activeTaskId;

  return (
    <div style={{ padding: 32 }}>
      <Title level={4} className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>
        记忆图谱
      </Title>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />

      {!hasActiveWork ? (
        <Empty
          description={<span className="cn-tag">暂无活跃任务，请在对话页面发起新任务</span>}
          style={{ marginTop: 60 }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <SourceVisualization />
        </div>
      )}
    </div>
  );
}
