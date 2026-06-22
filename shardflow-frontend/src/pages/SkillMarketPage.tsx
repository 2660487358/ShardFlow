import { useState, useEffect, useCallback } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Button, Card, Tag, List, Typography, Skeleton, message,
  Modal, Form, Input, Space, Popconfirm, Upload, Empty, Spin,
  Select, Pagination, Row, Col,
} from 'antd';
import {
  ThunderboltOutlined, PlusOutlined, DeleteOutlined, EditOutlined,
  UploadOutlined, SearchOutlined, PauseCircleOutlined, PlayCircleOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import type { Skill, SkillQueryParams } from '@/types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

const SKILL_TYPES = [
  { value: 'prompt', label: 'Prompt' },
  { value: 'tool', label: 'Tool' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'workflow', label: 'Workflow' },
];

const TRUST_TIERS = [
  { value: 'personal', label: '个人' },
  { value: 'team', label: '团队' },
  { value: 'official', label: '官方' },
];

const STATUSES = [
  { value: 'draft', label: '草稿' },
  { value: 'reviewing', label: '审核中' },
  { value: 'published', label: '已发布' },
  { value: 'deprecated', label: '已停用' },
  { value: 'archived', label: '已归档' },
];

interface SkillFormValues {
  skill_name: string;
  description: string;
  skill_type: string;
  trust_tier: string;
  category: string;
  trigger_keywords?: string;
}

export default function SkillMarketPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const {
    skills, skillTotal, skillLoading, skillCategories,
    syncSkills, syncSkillCategories, addSkill, removeSkill,
    updateSkillInStore, toggleSkillStatusInStore,
  } = useStore();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  // 查询条件
  const [query, setQuery] = useState<SkillQueryParams>({
    keyword: '',
    category: undefined,
    status: undefined,
    trust_tier: undefined,
    skill_type: undefined,
    page: 1,
    size: 12,
  });

  const fetchData = useCallback(async () => {
    if (!isAuthenticated) return;
    await syncSkills(query);
  }, [isAuthenticated, query, syncSkills]);

  useEffect(() => {
    if (!isAuthenticated) return;
    syncSkillCategories();
  }, [isAuthenticated, syncSkillCategories]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearch = () => {
    setQuery((prev) => ({ ...prev, page: 1 }));
  };

  const handlePageChange = (page: number) => {
    setQuery((prev) => ({ ...prev, page }));
  };

  const openAddModal = () => {
    setEditingSkill(null);
    form.resetFields();
    form.setFieldsValue({
      skill_type: 'prompt',
      trust_tier: 'personal',
    });
    setModalOpen(true);
  };

  const openEditModal = (skill: Skill) => {
    setEditingSkill(skill);
    form.setFieldsValue({
      skill_name: skill.skill_name,
      description: skill.description,
      skill_type: skill.skill_type,
      trust_tier: skill.trust_tier,
      category: skill.category,
      trigger_keywords: skill.trigger_keywords?.join(', ') || '',
    });
    setModalOpen(true);
  };

  const buildPayload = (values: SkillFormValues): Record<string, unknown> => {
    const triggerKeywords = values.trigger_keywords
      ? values.trigger_keywords.split(/[,，]/).map((k) => k.trim()).filter(Boolean)
      : [];
    return {
      skill_name: values.skill_name,
      description: values.description,
      skill_type: values.skill_type,
      trust_tier: values.trust_tier,
      category: values.category,
      trigger_keywords: triggerKeywords,
      input_schema: {},
      output_schema: {},
      config: {},
      cost_estimate: { avg_input_tokens: 0, avg_output_tokens: 0, avg_latency_ms: 0 },
      tags: [],
    };
  };

  const handleSubmit = async (values: SkillFormValues) => {
    setSaving(true);
    try {
      if (editingSkill) {
        await updateSkillInStore(editingSkill.skill_code, buildPayload(values));
      } else {
        // 乐观更新：临时 skill_code 用于列表展示
        const tempCode = `TEMP-${Date.now()}`;
        addSkill({ ...buildPayload(values), skill_code: tempCode } as unknown as Omit<Skill, 'id' | 'skill_code' | 'created_at' | 'updated_at'>);
      }
      setModalOpen(false);
      form.resetFields();
      setEditingSkill(null);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (skillCode: string) => {
    removeSkill(skillCode);
  };

  const handleToggleStatus = (skill: Skill) => {
    const nextStatus = skill.status === 'published' ? 'deprecated' : 'published';
    toggleSkillStatusInStore(skill.skill_code, nextStatus);
  };

  const beforeUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const { importSkills } = await import('@/api/client');
        const result = await importSkills(file);
        message.success(`导入完成：创建 ${result.created}，跳过 ${result.skipped}，失败 ${result.failed}`);
        fetchData();
      } catch (err: unknown) {
        message.error(`导入失败: ${err instanceof Error ? err.message : '请检查文件格式'}`);
      }
    };
    reader.readAsText(file);
    return false;
  };

  const statusLabel = (status: string) => {
    const found = STATUSES.find((s) => s.value === status);
    return found ? found.label : status;
  };

  const statusColor = (status: string) => {
    switch (status) {
      case 'published': return 'success';
      case 'deprecated': return 'default';
      case 'draft': return 'processing';
      case 'reviewing': return 'warning';
      case 'archived': return 'error';
      default: return 'default';
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用 Skills 管理功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>Skills</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理你的 Skills，支持新建、编辑、删除、导入和多条件筛选</Text>
          </div>
          <Space>
            <Upload beforeUpload={beforeUpload} showUploadList={false} accept=".json">
              <Button icon={<UploadOutlined />} className="cn-sans">
                导入 Skill
              </Button>
            </Upload>
            <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal} className="cn-sans">
              新建 Skill
            </Button>
          </Space>
        </div>

        {/* 筛选栏 */}
        <Row gutter={[12, 12]} style={{ marginBottom: 24 }} align="middle">
          <Col xs={24} sm={12} md={8} lg={5}>
            <Input
              prefix={<SearchOutlined style={{ color: 'var(--ink-faint)' }} />}
              placeholder="搜索名称或描述..."
              value={query.keyword}
              onChange={(e) => setQuery((prev) => ({ ...prev, keyword: e.target.value }))}
              onPressEnter={handleSearch}
              allowClear
            />
          </Col>
          <Col xs={12} sm={6} md={4} lg={3}>
            <Select
              placeholder="分类"
              allowClear
              style={{ width: '100%' }}
              value={query.category}
              onChange={(v) => setQuery((prev) => ({ ...prev, category: v, page: 1 }))}
            >
              {skillCategories.map((c) => (
                <Option key={c} value={c}>{c}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={12} sm={6} md={4} lg={3}>
            <Select
              placeholder="状态"
              allowClear
              style={{ width: '100%' }}
              value={query.status}
              onChange={(v) => setQuery((prev) => ({ ...prev, status: v, page: 1 }))}
            >
              {STATUSES.map((s) => (
                <Option key={s.value} value={s.value}>{s.label}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={12} sm={6} md={4} lg={3}>
            <Select
              placeholder="信任等级"
              allowClear
              style={{ width: '100%' }}
              value={query.trust_tier}
              onChange={(v) => setQuery((prev) => ({ ...prev, trust_tier: v, page: 1 }))}
            >
              {TRUST_TIERS.map((t) => (
                <Option key={t.value} value={t.value}>{t.label}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={12} sm={6} md={4} lg={3}>
            <Select
              placeholder="执行模式"
              allowClear
              style={{ width: '100%' }}
              value={query.skill_type}
              onChange={(v) => setQuery((prev) => ({ ...prev, skill_type: v, page: 1 }))}
            >
              {SKILL_TYPES.map((t) => (
                <Option key={t.value} value={t.value}>{t.label}</Option>
              ))}
            </Select>
          </Col>
          <Col xs={24} sm={12} md={8} lg={4}>
            <Button type="primary" onClick={handleSearch} icon={<SearchOutlined />}>
              查询
            </Button>
          </Col>
        </Row>

        {/* Skills 列表 */}
        {skillLoading ? (
          <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
        ) : skills.length === 0 ? (
          <Empty description={query.keyword ? '未找到匹配的 Skill' : '还没有 Skill，点击上方按钮创建或导入'} />
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
              {skills.map((skill) => (
                <Card
                  key={skill.skill_code}
                  hoverable
                  style={{ borderColor: skill.status === 'published' ? 'var(--accent)' : undefined }}
                  actions={[
                    <Button
                      key="edit"
                      type="text"
                      icon={<EditOutlined />}
                      onClick={() => openEditModal(skill)}
                    />,
                    <Button
                      key="toggle"
                      type="text"
                      icon={skill.status === 'published' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                      onClick={() => handleToggleStatus(skill)}
                    />,
                    <Popconfirm
                      key="delete"
                      title="确定删除此 Skill？"
                      description={`确定要删除 Skill「${skill.skill_name}」吗？`}
                      onConfirm={() => handleDelete(skill.skill_code)}
                    >
                      <Button type="text" icon={<DeleteOutlined />} danger />
                    </Popconfirm>,
                  ]}
                >
                  <Card.Meta
                    avatar={
                      <div style={{
                        width: 40, height: 40, borderRadius: 10,
                        background: skill.status === 'published' ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: skill.status === 'published' ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                      }}>
                        <ThunderboltOutlined style={{ fontSize: 20, color: skill.status === 'published' ? 'var(--accent-warm)' : '#c9a87c' }} />
                      </div>
                    }
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span>{skill.skill_name}</span>
                        <Tag>v{skill.current_version}</Tag>
                        <Tag color={statusColor(skill.status)} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                          {statusLabel(skill.status)}
                        </Tag>
                        {skill.source === 'IMPORTED' && <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>导入</Tag>}
                      </div>
                    }
                    description={
                      <>
                        <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                          {skill.description || '暂无描述'}
                        </Paragraph>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                          <Tag color="default" style={{ fontSize: 11 }}>{skill.skill_type}</Tag>
                          <Tag color="default" style={{ fontSize: 11 }}>{skill.trust_tier}</Tag>
                          {skill.category && <Tag color="default" style={{ fontSize: 11 }}>{skill.category}</Tag>}
                        </div>
                        <div style={{ display: 'flex', gap: 16 }}>
                          <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
                            {new Date(skill.created_at).toLocaleDateString('zh-CN')}
                          </Text>
                        </div>
                      </>
                    }
                  />
                </Card>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
              <Pagination
                current={query.page}
                pageSize={query.size}
                total={skillTotal}
                onChange={handlePageChange}
                showSizeChanger={false}
              />
            </div>
          </>
        )}
      </div>

      {/* 新建/编辑 Skill Modal */}
      <Modal
        title={editingSkill ? '编辑 Skill' : '新建 Skill'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingSkill(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText={editingSkill ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={saving}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ skill_type: 'prompt', trust_tier: 'personal' }}
        >
          <Form.Item
            name="skill_name"
            label="名称"
            rules={[{ required: true, message: '请输入 Skill 名称' }]}
          >
            <Input placeholder="Skill 名称" maxLength={128} showCount />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true, message: '请输入 Skill 描述' }]}
          >
            <TextArea rows={3} placeholder="Skill 功能描述" maxLength={2000} showCount />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="skill_type"
                label="执行模式"
                rules={[{ required: true, message: '请选择执行模式' }]}
              >
                <Select>
                  {SKILL_TYPES.map((t) => (
                    <Option key={t.value} value={t.value}>{t.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="trust_tier"
                label="信任等级"
                rules={[{ required: true, message: '请选择信任等级' }]}
              >
                <Select>
                  {TRUST_TIERS.map((t) => (
                    <Option key={t.value} value={t.value}>{t.label}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="category" label="分类">
            <Input placeholder="例如：code_analysis" />
          </Form.Item>
          <Form.Item name="trigger_keywords" label="触发关键词">
            <Input placeholder="用逗号分隔，例如：代码, 审查, review" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
