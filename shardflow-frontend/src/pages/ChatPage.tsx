import { useEffect } from 'react';
import { Row, Col, Select, Button, Modal, Input, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchTasks, createTask } from '@/api/client';
import ChatPanel from '@/components/chat/ChatPanel';
import ShardViewer from '@/components/shard/ShardViewer';
import StrategyPanel from '@/components/strategy/StrategyPanel';
import SourceVisualization from '@/components/source/SourceVisualization';
import { useState } from 'react';

const { Title } = Typography;

export default function ChatPage() {
  const { tasks, setTasks, activeTaskId, setActiveTask, activeSessionId } = useStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  useEffect(() => {
    fetchTasks().then((data) => setTasks(data as never[])).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      const result = await createTask(newTitle);
      setActiveTask(result.task_id);
      setModalOpen(false);
      setNewTitle('');
      const data = await fetchTasks();
      setTasks(data as never[]);
    } catch { /* ignore */ }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>对话</Title>
        <div style={{ display: 'flex', gap: 8 }}>
          <Select
            placeholder="选择任务"
            value={activeTaskId}
            onChange={(val) => setActiveTask(val)}
            style={{ width: 240 }}
            options={tasks.map((t) => ({ label: t.title || t.task_id, value: t.task_id }))}
          />
          <Button icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建任务</Button>
        </div>
      </div>

      <Row gutter={16}>
        <Col span={16}>
          <ChatPanel key={activeTaskId} />
        </Col>
        <Col span={8}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <ShardViewer />
            <StrategyPanel />
            <SourceVisualization />
          </div>
        </Col>
      </Row>

      <Modal title="新建探索任务" open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)}>
        <Input placeholder="任务标题，如：理清Dubbo注册链路" value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)} />
      </Modal>
    </div>
  );
}
