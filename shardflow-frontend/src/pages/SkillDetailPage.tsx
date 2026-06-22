import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Button, Card, Tag, Typography, Spin, Empty, Table, Space, Modal, Input, message,
  Popconfirm, Descriptions, Alert,
} from 'antd';
import {
  ArrowLeftOutlined, ThunderboltOutlined, EditOutlined, DeleteOutlined,
  PlayCircleOutlined, RollbackOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import {
  fetchSkillDetail, fetchSkillVersions, publishSkillVersion, rollbackSkillVersion,
  deleteSkill, fetchSkillAgents,
} from '@/api/client';
import type { SkillDetail, SkillVersion, SkillDetailAgentRef, SkillDetailVersionRef } from '@/types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const statusLabels: Record<string, string> = {
  draft: '草稿', reviewing: '审核中', published: '已发布', deprecated: '已停用', archived: '已归档',
};

const statusColors: Record<string, string> = {
  draft: 'processing', reviewing: 'warning', published: 'success', deprecated: 'default', archived: 'error',
};

const versionStatusLabels: Record<string, string> = {
  draft: '草稿', staging: '预发布', production: '生产', rolled_back: '已回滚',
};

const versionStatusColors: Record<string, string> = {
  draft: 'default', staging: 'warning', production: 'success', rolled_back: 'error',
};

export default function SkillDetailPage() {
  const { skillCode } = useParams<{ skillCode: string }>();
  const navigate = useNavigate();
  const { token, skillDetail: cachedDetail, setSkillDetail, setSkillDetailLoading } = useStore();

  const [detail, setDetail] = useState<SkillDetail | null>(cachedDetail);
  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<SkillVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [agents, setAgents] = useState<SkillDetailAgentRef[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishTarget, setPublishTarget] = useState<{ versionTag: string; promotionType: string } | null>(null);
  const [changeLog, setChangeLog] = useState('');
  const [publishing, setPublishing] = useState(false);

  const loadDetail = async () => {
    if (!skillCode) return;
    setLoading(true);
    setSkillDetailLoading(true);
    try {
      const data = await fetchSkillDetail(skillCode);
      setDetail(data);
      setSkillDetail(data);
    } catch (err: unknown) {
      message.error(`加载 Skill 详情失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setLoading(false);
      setSkillDetailLoading(false);
    }
  };

  const loadVersions = async () => {
    if (!skillCode) return;
    setVersionsLoading(true);
    try {
      const data = await fetchSkillVersions(skillCode);
      setVersions(data);
    } catch (err: unknown) {
      message.error(`加载版本历史失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setVersionsLoading(false);
    }
  };

  const loadAgents = async () => {
    if (!skillCode) return;
    setAgentsLoading(true);
    try {
      const data = await fetchSkillAgents(skillCode);
      setAgents(data);
    } catch (err: unknown) {
      message.error(`加载关联 Agent 失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setAgentsLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
    loadVersions();
    loadAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillCode]);

  const handleDelete = async () => {
    if (!skillCode) return;
    try {
      await deleteSkill(skillCode);
      message.success('Skill 已删除');
      navigate('/skills');
    } catch (err: unknown) {
      message.error(`删除失败: ${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const openPublish = (versionTag: string, promotionType: string) => {
    setPublishTarget({ versionTag, promotionType });
    setChangeLog('');
    setPublishOpen(true);
  };

  const handlePublish = async () => {
    if (!skillCode || !publishTarget) return;
    if (!changeLog.trim()) {
      message.warning('请输入变更说明');
      return;
    }
    setPublishing(true);
    try {
      await publishSkillVersion(skillCode, publishTarget.versionTag, changeLog, publishTarget.promotionType);
      message.success(`版本 ${publishTarget.versionTag} 已发布为 ${publishTarget.promotionType}`);
      setPublishOpen(false);
      await loadDetail();
      await loadVersions();
    } catch (err: unknown) {
      message.error(`发布失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setPublishing(false);
    }
  };

  const handleRollback = async (versionTag: string) => {
    if (!skillCode) return;
    try {
      await rollbackSkillVersion(skillCode, versionTag);
      message.success('已回滚');
      await loadDetail();
      await loadVersions();
    } catch (err: unknown) {
      message.error(`回滚失败: ${err instanceof Error ? err.message : '未知错误'}`);
    }
  };

  const versionColumns = [
    { title: '版本号', dataIndex: 'version_tag', key: 'version_tag' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={versionStatusColors[s] || 'default'}>{versionStatusLabels[s] || s}</Tag>,
    },
    { title: '变更说明', dataIndex: 'change_log', key: 'change_log', ellipsis: true },
    { title: '发布者', dataIndex: 'promoted_by', key: 'promoted_by', render: (v: number | null) => v ?? '-' },
    {
      title: '发布时间', dataIndex: 'promoted_at', key: 'promoted_at',
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: SkillDetailVersionRef) => (
        <Space>
          {record.status === 'draft' && (
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => openPublish(record.version_tag, 'staging')}
            >
              发布为 staging
            </Button>
          )}
          {record.status === 'staging' && (
            <Button
              type="text"
              size="small"
              icon={<PlayCircleOutlined />}
              onClick={() => openPublish(record.version_tag, 'production')}
            >
              发布为 production
            </Button>
          )}
          {record.status === 'production' && (
            <Popconfirm
              title="回滚到此版本？"
              onConfirm={() => handleRollback(record.version_tag)}
            >
              <Button type="text" size="small" icon={<RollbackOutlined />}>回滚</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const agentColumns = [
    { title: 'Agent 名称', dataIndex: 'name', key: 'name' },
    { title: 'Agent 编码', dataIndex: 'agent_code', key: 'agent_code' },
    {
      title: '绑定类型', dataIndex: 'binding_type', key: 'binding_type',
      render: (v: string) => <Tag color={v === 'required' ? 'success' : 'default'}>{v}</Tag>,
    },
    { title: '优先级', dataIndex: 'priority', key: 'priority' },
  ];

  if (!token) {
    return <div style={{ padding: 48, textAlign: 'center' }}><Text type="secondary">请先登录</Text></div>;
  }

  if (loading || !detail) {
    return <div style={{ padding: 64, textAlign: 'center' }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/skills')} style={{ marginBottom: 16 }}>
          返回 Skills 列表
        </Button>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: detail.status === 'published' ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              border: detail.status === 'published' ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
            }}>
              <ThunderboltOutlined style={{ fontSize: 24, color: detail.status === 'published' ? 'var(--accent-warm)' : '#c9a87c' }} />
            </div>
            <div>
              <Title level={3} style={{ margin: 0 }}>{detail.skill_name}</Title>
              <Text type="secondary">{detail.skill_code}</Text>
            </div>
          </div>
          <Space>
            <Button icon={<EditOutlined />} onClick={() => navigate('/skills')}>
              编辑
            </Button>
            <Popconfirm title="确定删除此 Skill？" onConfirm={handleDelete}>
              <Button icon={<DeleteOutlined />} danger>删除</Button>
            </Popconfirm>
          </Space>
        </div>

        <Card style={{ marginBottom: 24 }}>
          <Descriptions title="基本信息" bordered column={2} size="small">
            <Descriptions.Item label="状态">
              <Tag color={statusColors[detail.status] || 'default'}>{statusLabels[detail.status] || detail.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="当前版本">{detail.current_version || '-'}</Descriptions.Item>
            <Descriptions.Item label="执行模式">{detail.skill_type}</Descriptions.Item>
            <Descriptions.Item label="信任等级">{detail.trust_tier}</Descriptions.Item>
            <Descriptions.Item label="分类">{detail.category || '-'}</Descriptions.Item>
            <Descriptions.Item label="来源">{detail.source}</Descriptions.Item>
            <Descriptions.Item label="触发关键词" span={2}>
              {detail.trigger_keywords?.length ? detail.trigger_keywords.map((k) => <Tag key={k}>{k}</Tag>) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="描述" span={2}>
              <Paragraph style={{ margin: 0 }}>{detail.description || '暂无描述'}</Paragraph>
            </Descriptions.Item>
            <Descriptions.Item label="标签" span={2}>
              {detail.tags?.length ? detail.tags.map((t) => <Tag key={t}>{t}</Tag>) : '-'}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Card title="版本历史" style={{ marginBottom: 24 }}>
          <Table
            columns={versionColumns}
            dataSource={versions}
            rowKey="version_tag"
            loading={versionsLoading}
            pagination={false}
            size="small"
            locale={{ emptyText: <Empty description="暂无版本" /> }}
          />
        </Card>

        <Card title="关联 Agent">
          <Table
            columns={agentColumns}
            dataSource={agents}
            rowKey="id"
            loading={agentsLoading}
            pagination={false}
            size="small"
            locale={{ emptyText: <Empty description="暂无 Agent 绑定" /> }}
          />
        </Card>

        <Modal
          title="发布版本"
          open={publishOpen}
          onCancel={() => setPublishOpen(false)}
          onOk={handlePublish}
          confirmLoading={publishing}
        >
          <Alert
            message={`将版本 ${publishTarget?.versionTag ?? ''} 发布为 ${publishTarget?.promotionType ?? ''}`}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <TextArea
            rows={4}
            placeholder="请输入变更说明（必填）"
            value={changeLog}
            onChange={(e) => setChangeLog(e.target.value)}
            maxLength={500}
            showCount
          />
        </Modal>
      </div>
    </div>
  );
}
