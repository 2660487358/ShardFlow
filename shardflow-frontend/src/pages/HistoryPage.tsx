import { useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Result, Button, Card, List, Tag, Typography, Skeleton, message } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchTaskHistory } from '@/api/client';

const { Text } = Typography;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

interface SessionSummary {
  id: string;
  session_seq: number;
  date: string;
  source_port: string;
  status: string;
  summary: string;
}

export default function HistoryPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const { sessionHistory, setSessionHistory, setActiveTask } = useStore();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    setLoading(true);
    fetchTaskHistory()
      .then((data) => {
        const list = Array.isArray(data) ? data : (data as Record<string, unknown>)?.list || (data as Record<string, unknown>)?.records || [];
        setSessionHistory(list as SessionSummary[]);
      })
      .catch(() => { message.error('获取历史记录失败'); })
      .finally(() => { setLoading(false); });
  }, [isAuthenticated, setSessionHistory]);

  const handleResume = (item: SessionSummary) => {
    setActiveTask(item.id, item.id);
    message.success(`已恢复会话: ${item.summary || item.id}`);
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Result
          icon={<span style={{ fontSize: 48, opacity: 0.6 }}>📜</span>}
          title={<span className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>需要登录</span>}
          subTitle={<span className="cn-tag">登录后查看历史对话记录</span>}
          extra={
            <Button type="primary" onClick={onLoginRequired}
              style={{ background: 'var(--ink)', border: 'none', boxShadow: '0 4px 12px rgba(42,37,32,0.15)', fontFamily: 'var(--font-sans)', letterSpacing: '0.08em' }}>
              登录
            </Button>
          }
        />
      </div>
    );
  }

  const statusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'ACTIVE': case 'RUNNING': return 'processing';
      case 'COMPLETED': case 'DONE': return 'success';
      case 'FAILED': case 'ERROR': return 'error';
      default: return 'default';
    }
  };

  return (
    <div style={{ padding: 32, maxWidth: 800, margin: '0 auto' }}>
      <h2 className="cn-title" style={{ fontWeight: 600, color: 'var(--ink)', letterSpacing: '0.05em' }}>会话历史</h2>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />

      {loading ? (
        <Card style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)' }}>
          <Skeleton active paragraph={{ rows: 5 }} />
        </Card>
      ) : sessionHistory.length === 0 ? (
        <Card style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)', textAlign: 'center', padding: 40 }}>
          <HistoryOutlined style={{ fontSize: 32, color: 'var(--ink-faint)', marginBottom: 12 }} />
          <p className="cn-tag">暂无历史对话</p>
        </Card>
      ) : (
        <List
          dataSource={sessionHistory}
          renderItem={(item: SessionSummary) => (
            <Card
              key={item.id}
              size="small"
              hoverable
              onClick={() => handleResume(item)}
              style={{ marginBottom: 12, background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)', cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Text strong className="cn-sans" style={{ color: 'var(--ink)', fontSize: 15 }}>
                    {item.summary || `会话 #${item.session_seq}`}
                  </Text>
                  <Tag style={{ marginLeft: 8 }}>#{item.session_seq}</Tag>
                  <Tag color={statusColor(item.status)} style={{ marginLeft: 4 }}>
                    {item.status || '未知'}
                  </Tag>
                </div>
              </div>
              <div style={{ marginTop: 4, display: 'flex', gap: 16 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{item.date || '-'}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>来源: {item.source_port || 'Web'}</Text>
              </div>
            </Card>
          )}
        />
      )}
    </div>
  );
}
