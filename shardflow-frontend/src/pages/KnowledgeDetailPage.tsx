import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Table, Button, Upload, Typography, Tag, message, Space, Progress, Tooltip } from 'antd';
import { UploadOutlined, ArrowLeftOutlined, DeleteOutlined, LinkOutlined, DisconnectOutlined } from '@ant-design/icons';
import { fetchKbDocuments, uploadKbDocument, deleteKbDocument } from '@/api/client';
import { useStore } from '@/store';
import type { KbDocument } from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text } = Typography;

const statusColors: Record<string, string> = {
  PENDING: 'default', PARSING: 'processing', EMBEDDING: 'processing',
  READY: 'success', ERROR: 'error',
};

const statusLabels: Record<string, string> = {
  PENDING: '等待中', PARSING: '解析中', EMBEDDING: '向量化中', READY: '就绪', ERROR: '失败',
};

export default function KnowledgeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { kbCollections, token, kbActiveMount, setKbActiveMount } = useStore();
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const collection = (Array.isArray(kbCollections) ? kbCollections : []).find((c) => c.id === id);
  const isMounted = kbActiveMount.mounted && kbActiveMount.collectionId === id;

  const handleMountToggle = () => {
    if (isMounted) {
      setKbActiveMount({ mounted: false, collectionId: null, collectionName: '' });
      message.info('已取消挂载');
    } else if (collection) {
      setKbActiveMount({ mounted: true, collectionId: collection.id, collectionName: collection.name });
      message.success(`已将「${collection.name}」挂载到当前会话`);
    }
  };

  const loadDocs = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const list = await fetchKbDocuments(id);
      setDocs(list);
    } catch { message.error('加载文档失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadDocs(); }, [id]);

  useEffect(() => {
    const hasProcessing = docs.some((d) => ['PENDING', 'PARSING', 'EMBEDDING'].includes(d.status));
    if (!hasProcessing) return;
    const timer = setInterval(loadDocs, 3000);
    return () => clearInterval(timer);
  }, [docs]);

  const handleUpload = async (file: File) => {
    if (!id) return;
    setUploading(true);
    setUploadProgress(0);
    try {
      await uploadKbDocument(id, file, (pct) => setUploadProgress(pct));
      message.success(`${file.name} 上传成功，正在后台处理`);
      await loadDocs();
    } catch { message.error('上传失败'); }
    finally { setUploading(false); setUploadProgress(0); }
    return false;
  };

  const handleDelete = async (docId: string) => {
    try {
      await deleteKbDocument(docId);
      message.success('已删除');
      await loadDocs();
    } catch { message.error('删除失败'); }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const columns: ColumnsType<KbDocument> = [
    { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
    { title: '类型', dataIndex: 'file_type', key: 'file_type', width: 80, render: (t) => <Tag>{t.toUpperCase()}</Tag> },
    { title: '大小', dataIndex: 'file_size', key: 'file_size', width: 100, render: (s) => formatSize(s) },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 110,
      render: (s, record) => (
        <Space>
          <Tag color={statusColors[s] || 'default'}>{statusLabels[s] || s}</Tag>
          {s === 'ERROR' && record.error_msg && <Text type="danger" style={{ fontSize: 12 }}>{record.error_msg}</Text>}
        </Space>
      ),
    },
    { title: '上传时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: (t) => new Date(t).toLocaleString('zh-CN') },
    {
      title: '操作', key: 'action', width: 80,
      render: (_, record) => (
        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)} />
      ),
    },
  ];

  if (!token) {
    return <div style={{ padding: 48, textAlign: 'center' }}><Text type="secondary">请先登录</Text></div>;
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/kb')} style={{ marginBottom: 16 }}>
          返回知识库列表
        </Button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Title level={3} style={{ margin: 0 }}>{collection?.name || '知识库'}</Title>
            {isMounted && <Tag icon={<LinkOutlined />} color="green" style={{ fontSize: 13, padding: '4px 10px' }}>已挂载到当前会话</Tag>}
          </div>
          <Space>
            <Tooltip title={isMounted ? '取消挂载到当前会话' : '挂载到当前会话'}>
              <Button
                icon={isMounted ? <DisconnectOutlined /> : <LinkOutlined />}
                onClick={handleMountToggle}
                style={{
                  color: 'var(--accent-warm)',
                  border: '1px solid var(--accent)',
                  background: isMounted ? 'rgba(201,168,124,0.15)' : 'transparent',
                }}
              >
                {isMounted ? '取消挂载' : '挂载到会话'}
              </Button>
            </Tooltip>
            <Upload beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.md,.txt,.py,.java,.ts,.tsx,.js,.go,.rs,.yaml,.yml,.json,.xml">
              <Button type="primary" icon={<UploadOutlined />} loading={uploading}>上传文档</Button>
            </Upload>
          </Space>
        </div>

        {collection?.description && (
          <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 13 }}>{collection.description}</Text>
        )}

        {uploading && <Progress percent={uploadProgress} style={{ marginBottom: 16 }} />}
        <Table columns={columns} dataSource={docs} rowKey="id" loading={loading} pagination={{ pageSize: 20 }} size="middle" />
      </div>
    </div>
  );
}
