import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Modal, Input, Typography, Empty, Spin, message, Popconfirm, Tag, Tooltip } from 'antd';
import { PlusOutlined, BookOutlined, DeleteOutlined, EditOutlined, SearchOutlined, LinkOutlined, DisconnectOutlined, InboxOutlined, RollbackOutlined } from '@ant-design/icons';
import { fetchKbCollections, createKbCollection, updateKbCollection, deleteKbCollection, archiveKbCollection, unarchiveKbCollection } from '@/api/client';
import { useStore } from '@/store';
import type { KbCollection } from '@/types';

const { Title, Text, Paragraph } = Typography;

export default function KnowledgePage() {
  const { kbCollections, setKbCollections, kbLoading, setKbLoading, kbActiveMount, setKbActiveMount } = useStore();
  const navigate = useNavigate();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingCol, setEditingCol] = useState<KbCollection | null>(null);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchText, setSearchText] = useState('');

  const token = useStore((s) => s.token);

  useEffect(() => {
    loadCollections();
  }, []);

  const loadCollections = async () => {
    setKbLoading(true);
    try {
      const cols = await fetchKbCollections();
      const list = Array.isArray(cols) ? cols : (Array.isArray((cols as Record<string, unknown>)?.collections) ? (cols as Record<string, unknown>).collections as KbCollection[] : []);
      setKbCollections(list);
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

  const handleEdit = (col: KbCollection) => {
    setEditingCol(col);
    setNewName(col.name);
    setNewDesc(col.description);
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editingCol || !newName.trim()) return;
    setSaving(true);
    try {
      await updateKbCollection(editingCol.id, { name: newName.trim(), description: newDesc.trim() });
      message.success('更新成功');
      setEditModalOpen(false);
      setEditingCol(null);
      setNewName('');
      setNewDesc('');
      await loadCollections();
    } catch { message.error('更新失败'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteKbCollection(id);
      message.success('已删除');
      // 如果删除的是当前挂载的知识库，取消挂载
      if (kbActiveMount.collectionId === id) {
        setKbActiveMount({ mounted: false, collectionId: null, collectionName: '' });
      }
      await loadCollections();
    } catch { message.error('删除失败'); }
  };

  const handleMount = (col: KbCollection) => {
    if (kbActiveMount.mounted && kbActiveMount.collectionId === col.id) {
      setKbActiveMount({ mounted: false, collectionId: null, collectionName: '' });
      message.info('已取消挂载');
    } else {
      setKbActiveMount({ mounted: true, collectionId: col.id, collectionName: col.name });
      message.success(`已将「${col.name}」挂载到当前会话`);
    }
  };

  const isMounted = (col: KbCollection) => kbActiveMount.mounted && kbActiveMount.collectionId === col.id;

  const handleArchive = async (col: KbCollection) => {
    try {
      await archiveKbCollection(col.id);
      // 如果归档的是当前挂载的知识库，取消挂载
      if (kbActiveMount.collectionId === col.id) {
        setKbActiveMount({ mounted: false, collectionId: null, collectionName: '' });
      }
      message.success(`已归档「${col.name}」`);
      await loadCollections();
    } catch { message.error('归档失败'); }
  };

  const handleUnarchive = async (col: KbCollection) => {
    try {
      await unarchiveKbCollection(col.id);
      message.success(`已解档「${col.name}」`);
      await loadCollections();
    } catch { message.error('解档失败'); }
  };

  const safeCollections = Array.isArray(kbCollections) ? kbCollections : [];
  const filteredCollections = safeCollections.filter((col) => {
    if (!searchText.trim()) return true;
    const q = searchText.toLowerCase();
    return col.name.toLowerCase().includes(q) || (col.description || '').toLowerCase().includes(q);
  });

  if (!token) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用知识库功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>知识库</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理你的知识库，挂载到会话中让 AI 基于你的知识回答</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新建知识库
          </Button>
        </div>

        {/* 搜索栏 + 挂载状态 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Input
            prefix={<SearchOutlined style={{ color: 'var(--ink-faint)' }} />}
            placeholder="搜索知识库..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ maxWidth: 320 }}
          />
          {kbActiveMount.mounted && (
            <Tag
              icon={<LinkOutlined />}
              color="green"
              style={{ fontSize: 13, padding: '4px 10px', borderRadius: 6 }}
            >
              已挂载：{kbActiveMount.collectionName}
            </Tag>
          )}
        </div>

        {/* 知识库列表 */}
        {kbLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
        ) : filteredCollections.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的知识库' : '还没有知识库，点击上方按钮创建'} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {filteredCollections.map((col) => (
              <Card
                key={col.id}
                hoverable
                onClick={() => navigate(`/kb/${col.id}`)}
                style={{
                  borderColor: isMounted(col) ? 'var(--accent)' : undefined,
                  boxShadow: isMounted(col) ? '0 0 0 1px var(--accent)' : undefined,
                }}
                actions={[
                  <Tooltip key="mount" title={isMounted(col) ? '取消挂载' : '挂载到当前会话'}>
                    <Button
                      icon={isMounted(col) ? <LinkOutlined /> : <DisconnectOutlined />}
                      onClick={(e) => { e.stopPropagation(); handleMount(col); }}
                      style={{
                        color: 'var(--accent-warm)',
                        border: '1px solid var(--accent)',
                        background: isMounted(col) ? 'rgba(201,168,124,0.15)' : 'transparent',
                      }}
                    />
                  </Tooltip>,
                  <Button
                    key="edit"
                    type="text"
                    icon={<EditOutlined />}
                    onClick={(e) => { e.stopPropagation(); handleEdit(col); }}
                  />,
                  col.status === 'ARCHIVED' ? (
                    <Popconfirm
                      key="unarchive"
                      title="确定解档此知识库？"
                      description="解档后可以继续上传文档和挂载使用"
                      onConfirm={(e) => { e?.stopPropagation(); handleUnarchive(col); }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button type="text" icon={<RollbackOutlined />} onClick={(e) => e.stopPropagation()} />
                    </Popconfirm>
                  ) : (
                    <Popconfirm
                      key="archive"
                      title="确定归档此知识库？"
                      description="归档后将无法上传文档，且会自动取消挂载"
                      onConfirm={(e) => { e?.stopPropagation(); handleArchive(col); }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button type="text" icon={<InboxOutlined />} onClick={(e) => e.stopPropagation()} />
                    </Popconfirm>
                  ),
                  <Popconfirm
                    key="delete"
                    title="确定删除此知识库？"
                    description="删除后知识库中的所有文档和片段将无法恢复"
                    onConfirm={(e) => { e?.stopPropagation(); handleDelete(col.id); }}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button type="text" icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                  </Popconfirm>,
                ]}
              >
                <Card.Meta
                  avatar={
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: isMounted(col) ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: isMounted(col) ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                    }}>
                      <BookOutlined style={{ fontSize: 20, color: isMounted(col) ? 'var(--accent-warm)' : '#c9a87c' }} />
                    </div>
                  }
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{col.name}</span>
                      {isMounted(col) && <Tag color="green" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>已挂载</Tag>}
                      <Tag color={col.status === 'ACTIVE' ? 'success' : 'default'} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                        {col.status === 'ACTIVE' ? '活跃' : '归档'}
                      </Tag>
                    </div>
                  }
                  description={
                    <>
                      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                        {col.description || '暂无描述'}
                      </Paragraph>
                      <div style={{ display: 'flex', gap: 16 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>{col.doc_count} 文档</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>{col.chunk_count} 片段</Text>
                        <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
                          {new Date(col.updated_at).toLocaleDateString('zh-CN')}
                        </Text>
                      </div>
                    </>
                  }
                />
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* 新建知识库 Modal */}
      <Modal
        title="新建知识库"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateModalOpen(false); setNewName(''); setNewDesc(''); }}
        confirmLoading={creating}
        okText="创建"
      >
        <Input
          placeholder="知识库名称"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          placeholder="描述（可选）"
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
          rows={3}
        />
      </Modal>

      {/* 编辑知识库 Modal */}
      <Modal
        title="编辑知识库"
        open={editModalOpen}
        onOk={handleSaveEdit}
        onCancel={() => { setEditModalOpen(false); setEditingCol(null); setNewName(''); setNewDesc(''); }}
        confirmLoading={saving}
        okText="保存"
      >
        <Input
          placeholder="知识库名称"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <Input.TextArea
          placeholder="描述（可选）"
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
          rows={3}
        />
      </Modal>
    </div>
  );
}
