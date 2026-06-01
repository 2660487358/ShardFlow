import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Table, Button, Upload, Typography, Tag, message, Space, Progress } from 'antd';
import { UploadOutlined, ArrowLeftOutlined, DeleteOutlined } from '@ant-design/icons';
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
  const { kbCollections, token } = useStore();
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const collection = kbCollections.find((c) => c.id === id);

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
    <div style={{ padding: '24px 32px', maxWidth: 1000, margin: '0 auto' }}>
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/kb')} style={{ marginBottom: 16 }}>
        返回知识库列表
      </Button>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>{collection?.name || '知识库'} · 文档管理</Title>
        <Upload beforeUpload={handleUpload} showUploadList={false} accept=".pdf,.docx,.md,.txt,.py,.java,.ts,.tsx,.js,.go,.rs,.yaml,.yml,.json,.xml">
          <Button type="primary" icon={<UploadOutlined />} loading={uploading}>上传文档</Button>
        </Upload>
      </div>
      {uploading && <Progress percent={uploadProgress} style={{ marginBottom: 16 }} />}
      <Table columns={columns} dataSource={docs} rowKey="id" loading={loading} pagination={{ pageSize: 20 }} size="middle" />
    </div>
  );
}
