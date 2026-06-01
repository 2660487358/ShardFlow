import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Modal, Input, Typography, Empty, Spin, message, Popconfirm } from 'antd';
import { PlusOutlined, BookOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { fetchKbCollections, createKbCollection, deleteKbCollection } from '@/api/client';
import { useStore } from '@/store';
import type { KbCollection } from '@/types';

const { Title, Text, Paragraph } = Typography;

export default function KnowledgePage() {
  const { kbCollections, setKbCollections, kbLoading, setKbLoading } = useStore();
  const navigate = useNavigate();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const token = useStore((s) => s.token);

  useEffect(() => {
    loadCollections();
  }, []);

  const loadCollections = async () => {
    setKbLoading(true);
    try {
      const cols = await fetchKbCollections();
      setKbCollections(cols);
    } catch { message.error('加载知识库失败'); }
    finally { setKbLoading(false); }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createKbCollection({ name: newName.trim(), description: newDesc.trim() });
      message.success('知识库创建成功');
      setCreateModalOpen(false);
      setNewName('');
      setNewDesc('');
      await loadCollections();
    } catch { message.error('创建失败'); }
    finally { setCreating(false); }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteKbCollection(id);
      message.success('已删除');
      await loadCollections();
    } catch { message.error('删除失败'); }
  };

  if (!token) {
    return <div style={{ padding: 48, textAlign: 'center' }}><Text type="secondary">请先登录</Text></div>;
  }

  return (
    <div style={{ padding: '24px 32px', maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>📚 我的知识库</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
          新建知识库
        </Button>
      </div>

      {kbLoading ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
      ) : kbCollections.length === 0 ? (
        <Empty description="还没有知识库，点击上方按钮创建" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {kbCollections.map((col) => (
            <Card
              key={col.id}
              hoverable
              onClick={() => navigate(`/kb/${col.id}`)}
              actions={[
                <EditOutlined key="edit" onClick={(e) => { e.stopPropagation(); }} />,
                <Popconfirm key="delete" title="确定删除此知识库？" onConfirm={(e) => { e?.stopPropagation(); handleDelete(col.id); }} onCancel={(e) => e?.stopPropagation()}>
                  <DeleteOutlined onClick={(e) => e.stopPropagation()} />
                </Popconfirm>,
              ]}
            >
              <Card.Meta
                avatar={<BookOutlined style={{ fontSize: 24, color: '#c9a87c' }} />}
                title={col.name}
                description={
                  <>
                    <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8 }}>{col.description || '暂无描述'}</Paragraph>
                    <Text type="secondary" style={{ fontSize: 12 }}>{col.doc_count} 文档 · {col.chunk_count} 片段</Text>
                  </>
                }
              />
            </Card>
          ))}
        </div>
      )}

      <Modal title="新建知识库" open={createModalOpen} onOk={handleCreate} onCancel={() => setCreateModalOpen(false)} confirmLoading={creating}>
        <Input placeholder="知识库名称" value={newName} onChange={(e) => setNewName(e.target.value)} style={{ marginBottom: 12 }} />
        <Input.TextArea placeholder="描述（可选）" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} rows={3} />
      </Modal>
    </div>
  );
}
