import { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Button, Card, Tag, List, Typography, message, Empty, Input, Modal, Form, Space, Popconfirm, Select, Slider,
} from 'antd';
import {
  RobotOutlined, PlusOutlined, DeleteOutlined, EditOutlined, CheckCircleOutlined, SearchOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchMcpTools, fetchAvailableModels } from '@/api/client';
import type { AgentConfig, AvailableModel } from '@/types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

const defaultSystemPrompt = '你是一个专业的AI助手，擅长分析问题和提供详细的解决方案。请根据用户的需求，给出准确、有用的回答。';

export default function AgentsPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const {
    agentConfigs, activeAgentId, addAgent, removeAgent, updateAgent, setActiveAgent,
  } = useStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentConfig | null>(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [saving, setSaving] = useState(false);
  const [availableTools, setAvailableTools] = useState<string[]>([
    'web_search', 'code_interpreter', 'file_reader', 'image_generator', 'data_analyzer',
  ]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);

  // Model options come entirely from the database via fetchAvailableModels() API
  const allModels = availableModels.map((m) => ({ key: m.key, label: m.label }));

  useEffect(() => {
    fetchMcpTools()
      .then((data) => {
        const tools = Array.isArray(data) ? data : (data as Record<string, unknown>)?.tools || [];
        if (Array.isArray(tools) && tools.length > 0) {
          const names = tools.map((t: Record<string, unknown>) => String(t.tool_name || t.name || ''));
          if (names.length > 0) setAvailableTools(names);
        }
      })
      .catch(() => {});
    fetchAvailableModels()
      .then((data) => setAvailableModels(data as AvailableModel[]))
      .catch(() => {});
  }, []);

  const filteredAgents = agentConfigs.filter((a) => {
    if (!searchText.trim()) return true;
    const q = searchText.toLowerCase();
    return a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q);
  });

  const handleAdd = (values: {
    name: string; description: string; system_prompt: string; model_id: string;
    temperature: number; max_tokens: number; tools: string[];
  }) => {
    setSaving(true);
    addAgent({ ...values, user_id: '' });
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
    message.success('Agent 创建成功');
  };

  const handleEdit = (values: {
    name: string; description: string; system_prompt: string; model_id: string;
    temperature: number; max_tokens: number; tools: string[];
  }) => {
    if (!editingAgent) return;
    setSaving(true);
    updateAgent(editingAgent.id, values);
    setEditingAgent(null);
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
    message.success('Agent 更新成功');
  };

  const handleDelete = (id: string) => {
    removeAgent(id);
    message.success('Agent 删除成功');
  };

  const handleActivate = (id: string) => {
    setActiveAgent(id);
    message.success('Agent 已激活');
  };

  const openAddModal = () => {
    setEditingAgent(null);
    form.setFieldsValue({
      name: '',
      description: '',
      system_prompt: defaultSystemPrompt,
      model_id: availableModels.length > 0 ? availableModels[0].key : '',
      temperature: 0.7,
      max_tokens: 4096,
      tools: [],
    });
    setModalOpen(true);
  };

  const openEditModal = (agent: AgentConfig) => {
    setEditingAgent(agent);
    form.setFieldsValue({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model_id: agent.model_id,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      tools: agent.tools,
    });
    setModalOpen(true);
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用 Agent 功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>Agent</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理你的 Agent 配置，设置模型、提示词和工具</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal} className="cn-sans">
            新建 Agent
          </Button>
        </div>

        {/* 搜索栏 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Input
            prefix={<SearchOutlined style={{ color: 'var(--ink-faint)' }} />}
            placeholder="搜索 Agent..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ maxWidth: 320 }}
          />
        </div>

        {/* Agent 列表 */}
        {filteredAgents.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的 Agent' : '还没有 Agent，点击上方按钮创建'} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {filteredAgents.map((agent) => (
              <Card
                key={agent.id}
                hoverable
                style={{
                  background: 'rgba(255,255,255,0.6)',
                  border: '1px solid var(--paper-dark)',
                  borderColor: activeAgentId === agent.id ? 'var(--accent)' : undefined,
                }}
                actions={[
                  activeAgentId !== agent.id && (
                    <Button
                      key="activate"
                      type="text"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleActivate(agent.id)}
                      style={{ color: 'var(--accent-warm)' }}
                    />
                  ),
                  <Button
                    key="edit"
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => openEditModal(agent)}
                  />,
                  <Popconfirm
                    key="delete"
                    title="确定删除此 Agent？"
                    description={`确定要删除 Agent「${agent.name}」吗？`}
                    onConfirm={() => handleDelete(agent.id)}
                  >
                    <Button type="text" icon={<DeleteOutlined />} danger />
                  </Popconfirm>,
                ].filter(Boolean)}
              >
                <Card.Meta
                  avatar={
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: activeAgentId === agent.id ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: activeAgentId === agent.id ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                    }}>
                      <RobotOutlined style={{ fontSize: 20, color: activeAgentId === agent.id ? 'var(--accent-warm)' : '#c9a87c' }} />
                    </div>
                  }
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{agent.name}</span>
                      {activeAgentId === agent.id && (
                        <Tag color="success" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>当前使用</Tag>
                      )}
                    </div>
                  }
                  description={
                    <>
                      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                        {agent.description || '暂无描述'}
                      </Paragraph>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        <Tag style={{ fontSize: 11, margin: 0 }}>{agent.model_id}</Tag>
                        <Tag style={{ fontSize: 11, margin: 0 }}>T={agent.temperature}</Tag>
                        {agent.tools.map((t) => (
                          <Tag key={t} style={{ fontSize: 11, margin: 0 }}>{t}</Tag>
                        ))}
                      </div>
                    </>
                  }
                />
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* 新建/编辑 Agent Modal */}
      <Modal
        title={editingAgent ? '编辑 Agent' : '新建 Agent'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingAgent(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText={editingAgent ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={saving}
        destroyOnClose
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={editingAgent ? handleEdit : handleAdd}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入 Agent 名称' }]}
          >
            <Input placeholder="Agent 名称" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
          >
            <Input placeholder="描述" />
          </Form.Item>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
          >
            <TextArea rows={3} placeholder="系统提示词" />
          </Form.Item>
          <Form.Item
            name="model_id"
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select placeholder="选择模型">
              {allModels.map((m) => (
                <Option key={m.key} value={m.key}>{m.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              name="temperature"
              label="Temperature"
              style={{ flex: 1 }}
            >
              <Slider min={0} max={2} step={0.1} />
            </Form.Item>
            <Form.Item
              name="max_tokens"
              label="Max Tokens"
              style={{ flex: 1 }}
            >
              <Slider min={256} max={16384} step={256} />
            </Form.Item>
          </div>
          <Form.Item
            name="tools"
            label="工具"
          >
            <Select mode="multiple" placeholder="选择工具">
              {availableTools.map((t) => (
                <Option key={t} value={t}>{t}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
