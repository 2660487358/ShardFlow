import { useEffect } from 'react';
import { Table, Tag, Button, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useStore } from '@/store';
import { fetchTasks } from '@/api/client';

const { Title } = Typography;

const statusColors: Record<string, string> = {
  PENDING: 'default', RUNNING: 'processing', COMPLETED: 'success', FAILED: 'error',
};

export default function TaskPage() {
  const { tasks, setTasks, setActiveTask } = useStore();
  const navigate = useNavigate();

  useEffect(() => {
    fetchTasks().then((data) => setTasks(data as never[])).catch(() => {});
  }, []);

  const columns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'task_id', ellipsis: true },
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColors[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: { task_id: string; session_id?: string }) => (
        <Button type="link" onClick={() => { setActiveTask(record.task_id, record.session_id); navigate('/chat'); }}>
          进入对话
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 32 }}>
      <Title level={4} className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>任务管理</Title>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />
      <Table columns={columns} dataSource={tasks} rowKey="task_id" size="middle" />
    </div>
  );
}
