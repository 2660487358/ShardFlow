import { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Button, Card, Tag, List, Typography, Skeleton, message,
  Modal, Form, Input, Space, Popconfirm, Upload, Empty, Spin,
} from 'antd';
import {
  ThunderboltOutlined, PlusOutlined, DeleteOutlined, EditOutlined,
  UploadOutlined, SearchOutlined,
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

interface Skill {
  id: string;
  name: string;
  description: string;
  version: string;
  status: 'active' | 'inactive';
  created_at: string;
  source: 'local' | 'imported';
}

const STORAGE_KEY = 'shardflow_skills';

function loadSkills(): Skill[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSkills(skills: Skill[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(skills));
}

export default function SkillMarketPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    setLoading(true);
    const timer = setTimeout(() => {
      setSkills(loadSkills());
      setLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [isAuthenticated]);

  const filteredSkills = skills.filter((s) => {
    if (!searchText.trim()) return true;
    const q = searchText.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q);
  });

  const handleAdd = (values: Omit<Skill, 'id' | 'created_at' | 'status' | 'source'>) => {
    setSaving(true);
    const now = new Date().toISOString();
    const newSkill: Skill = {
      ...values,
      id: `skill-${Date.now()}`,
      status: 'active',
      created_at: now,
      source: 'local',
    };
    const updated = [...skills, newSkill];
    setSkills(updated);
    saveSkills(updated);
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
    message.success('Skill 创建成功');
  };

  const handleEdit = (values: Omit<Skill, 'id' | 'created_at' | 'status' | 'source'>) => {
    if (!editingSkill) return;
    setSaving(true);
    const updated = skills.map((s) =>
      s.id === editingSkill.id ? { ...s, ...values } : s
    );
    setSkills(updated);
    saveSkills(updated);
    setEditingSkill(null);
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
    message.success('Skill 更新成功');
  };

  const handleDelete = (id: string) => {
    const updated = skills.filter((s) => s.id !== id);
    setSkills(updated);
    saveSkills(updated);
    message.success('Skill 删除成功');
  };

  const handleImport = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const imported = JSON.parse(content);
        const skillsToImport: Skill[] = Array.isArray(imported)
          ? imported.map((item: Record<string, unknown>, idx: number) => ({
              id: `skill-imported-${Date.now()}-${idx}`,
              name: String(item.name || '未命名 Skill'),
              description: String(item.description || ''),
              version: String(item.version || '1.0.0'),
              status: 'active',
              created_at: new Date().toISOString(),
              source: 'imported' as const,
            }))
          : [{
              id: `skill-imported-${Date.now()}`,
              name: String(imported.name || '未命名 Skill'),
              description: String(imported.description || ''),
              version: String(imported.version || '1.0.0'),
              status: 'active',
              created_at: new Date().toISOString(),
              source: 'imported' as const,
            }];
        const updated = [...skills, ...skillsToImport];
        setSkills(updated);
        saveSkills(updated);
        message.success(`成功导入 ${skillsToImport.length} 个 Skill`);
      } catch {
        message.error('导入失败，请检查文件格式');
      }
    };
    reader.readAsText(file);
    return false;
  };

  const openAddModal = () => {
    setEditingSkill(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (skill: Skill) => {
    setEditingSkill(skill);
    form.setFieldsValue({
      name: skill.name,
      description: skill.description,
      version: skill.version,
    });
    setModalOpen(true);
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
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>Skills</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理你的 Skills，支持新建、编辑、删除和本地导入</Text>
          </div>
          <Space>
            <Upload beforeUpload={handleImport} showUploadList={false} accept=".json">
              <Button icon={<UploadOutlined />} className="cn-sans">
                导入 Skill
              </Button>
            </Upload>
            <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal} className="cn-sans">
              新建 Skill
            </Button>
          </Space>
        </div>

        {/* 搜索栏 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Input
            prefix={<SearchOutlined style={{ color: 'var(--ink-faint)' }} />}
            placeholder="搜索 Skills..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ maxWidth: 320 }}
          />
        </div>

        {/* Skills 列表 */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
        ) : filteredSkills.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的 Skill' : '还没有 Skill，点击上方按钮创建或导入'} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {filteredSkills.map((skill) => (
              <Card
                key={skill.id}
                hoverable
                style={{ borderColor: skill.status === 'active' ? 'var(--accent)' : undefined }}
                actions={[
                  <Button
                    key="edit"
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => openEditModal(skill)}
                  />,
                  <Popconfirm
                    key="delete"
                    title="确定删除此 Skill？"
                    description={`确定要删除 Skill「${skill.name}」吗？`}
                    onConfirm={() => handleDelete(skill.id)}
                  >
                    <Button type="text" icon={<DeleteOutlined />} danger />
                  </Popconfirm>,
                ]}
              >
                <Card.Meta
                  avatar={
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: skill.status === 'active' ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: skill.status === 'active' ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                    }}>
                      <ThunderboltOutlined style={{ fontSize: 20, color: skill.status === 'active' ? 'var(--accent-warm)' : '#c9a87c' }} />
                    </div>
                  }
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{skill.name}</span>
                      <Tag>v{skill.version}</Tag>
                      <Tag color={skill.status === 'active' ? 'success' : 'default'} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                        {skill.status === 'active' ? '已启用' : '已停用'}
                      </Tag>
                      {skill.source === 'imported' && <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>导入</Tag>}
                    </div>
                  }
                  description={
                    <>
                      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                        {skill.description || '暂无描述'}
                      </Paragraph>
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
          onFinish={editingSkill ? handleEdit : handleAdd}
          initialValues={{ version: '1.0.0' }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入 Skill 名称' }]}
          >
            <Input placeholder="Skill 名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true, message: '请输入 Skill 描述' }]}
          >
            <TextArea rows={3} placeholder="Skill 功能描述" />
          </Form.Item>
          <Form.Item
            name="version"
            label="版本"
            rules={[{ required: true, message: '请输入版本号' }]}
          >
            <Input placeholder="例如：1.0.0" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
