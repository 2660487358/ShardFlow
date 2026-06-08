import { useState, useEffect } from 'react';
import { Modal, Input, Button, List, Typography, message, Slider, Switch, Select, Tag } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, RobotOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchMcpTools, fetchAvailableModels } from '@/api/client';
import type { AgentConfig, AvailableModel } from '@/types';

const { Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface Props {
  open: boolean;
  onClose: () => void;
}

const defaultSystemPrompt = '你是一个专业的AI助手，擅长分析问题和提供详细的解决方案。请根据用户的需求，给出准确、有用的回答。';

export default function AgentManageModal({ open, onClose }: Props) {
  const { agentConfigs, activeAgentId, addAgent, removeAgent, updateAgent, setActiveAgent } = useStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [availableTools, setAvailableTools] = useState<string[]>([
    'web_search', 'code_interpreter', 'file_reader', 'image_generator', 'data_analyzer',
  ]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [form, setForm] = useState({
    user_id: '',
    model_id: '',
    name: '',
    description: '',
    system_prompt: defaultSystemPrompt,
    temperature: 0.7,
    max_tokens: 4096,
    tools: [] as string[],
  });

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
  }, []);

  useEffect(() => {
    if (open) {
      fetchAvailableModels()
        .then((data) => {
          const models = data as AvailableModel[];
          setAvailableModels(models);
          // Auto-select first model if current selection is not in the list
          if (models.length > 0 && !models.some(m => m.key === form.model_id)) {
            setForm(f => ({ ...f, model_id: models[0].key }));
          }
        })
        .catch(() => {});
    }
  }, [open]);

  // Model options come entirely from the database via fetchAvailableModels() API
  const allModels: { key: string; label: string }[] = availableModels.map((m) => ({ key: m.key, label: m.label }));

  const resetForm = () => {
    setForm({
      user_id: '',
      model_id: availableModels.length > 0 ? availableModels[0].key : '',
      name: '',
      description: '',
      system_prompt: defaultSystemPrompt,
      temperature: 0.7,
      max_tokens: 4096,
      tools: [],
    });
    setEditingId(null);
  };

  const handleSubmit = () => {
    if (!form.name.trim()) {
      message.warning('请填写Agent名称');
      return;
    }
    if (editingId) {
      updateAgent(editingId, form);
      message.success('Agent已更新');
    } else {
      addAgent(form);
      message.success('Agent已创建');
    }
    resetForm();
  };

  const handleEdit = (agent: AgentConfig) => {
    setEditingId(agent.id);
    setForm({
      user_id: agent.user_id,
      model_id: agent.model_id,
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      tools: agent.tools,
    });
  };

  const handleDelete = (id: string) => {
    removeAgent(id);
    if (editingId === id) resetForm();
    message.success('Agent已删除');
  };

  const handleActivate = (id: string) => {
    setActiveAgent(id);
    message.success('Agent已激活');
  };

  return (
    <Modal
      open={open}
      onCancel={() => { resetForm(); onClose(); }}
      title={<span className="cn-sans" style={{ fontSize: 16, letterSpacing: '0.04em' }}>Agent管理</span>}
      footer={null}
      width={600}
      bodyStyle={{ padding: '20px 24px', maxHeight: '70vh', overflow: 'auto' }}
    >
      <div style={{ marginBottom: 24 }}>
        <div style={{ marginBottom: 12 }}>
          <Input
            placeholder="Agent名称"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            style={{ marginBottom: 8, fontFamily: 'var(--font-sans)' }}
          />
          <Input
            placeholder="描述"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            style={{ marginBottom: 8, fontFamily: 'var(--font-sans)' }}
          />
          <TextArea
            placeholder="系统提示词"
            value={form.system_prompt}
            onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
            rows={3}
            style={{ marginBottom: 8, fontFamily: 'var(--font-sans)' }}
          />
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <Select
              placeholder="选择模型"
              value={form.model_id}
              onChange={(v) => setForm((f) => ({ ...f, model_id: v }))}
              style={{ flex: 1 }}
            >
              {allModels.map((m) => (
                <Option key={m.key} value={m.key}>{m.label}</Option>
              ))}
            </Select>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
              <Text style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>Temperature</Text>
              <Slider
                min={0}
                max={2}
                step={0.1}
                value={form.temperature}
                onChange={(v) => setForm((f) => ({ ...f, temperature: v }))}
                style={{ flex: 1 }}
              />
              <Text style={{ fontSize: 12, color: 'var(--ink)', width: 32 }}>{form.temperature}</Text>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Text style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>Max Tokens</Text>
            <Slider
              min={256}
              max={16384}
              step={256}
              value={form.max_tokens}
              onChange={(v) => setForm((f) => ({ ...f, max_tokens: v }))}
              style={{ flex: 1 }}
            />
            <Text style={{ fontSize: 12, color: 'var(--ink)', width: 48 }}>{form.max_tokens}</Text>
          </div>
          <div style={{ marginBottom: 8 }}>
            <Text style={{ fontSize: 12, color: 'var(--ink-muted)', display: 'block', marginBottom: 4 }}>工具</Text>
            <Select
              mode="multiple"
              placeholder="选择工具"
              value={form.tools}
              onChange={(v) => setForm((f) => ({ ...f, tools: v }))}
              style={{ width: '100%' }}
            >
              {availableTools.map((t) => (
                <Option key={t} value={t}>{t}</Option>
              ))}
            </Select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          {editingId && (
            <Button onClick={resetForm} size="small">
              取消
            </Button>
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleSubmit}
            size="small"
            style={{ background: 'var(--ink)', borderColor: 'var(--ink)' }}
          >
            {editingId ? '保存' : '创建Agent'}
          </Button>
        </div>
      </div>

      <div className="hand-line" style={{ margin: '0 0 16px' }} />

      <List
        dataSource={agentConfigs}
        locale={{ emptyText: <Text className="cn-tag" style={{ color: 'var(--ink-muted)' }}>暂无Agent</Text> }}
        renderItem={(agent) => (
          <List.Item
            style={{
              padding: '12px 0',
              borderBottom: '1px solid var(--paper-dark)',
              background: activeAgentId === agent.id ? 'rgba(201,168,124,0.08)' : 'transparent',
              borderRadius: 8,
              paddingLeft: 8,
              paddingRight: 8,
            }}
            actions={[
              activeAgentId !== agent.id && (
                <Button
                  key="activate"
                  type="text"
                  icon={<CheckCircleOutlined />}
                  size="small"
                  onClick={() => handleActivate(agent.id)}
                  style={{ color: 'var(--accent-warm)' }}
                />
              ),
              <Button
                key="edit"
                type="text"
                icon={<EditOutlined />}
                size="small"
                onClick={() => handleEdit(agent)}
                style={{ color: 'var(--ink-faint)' }}
              />,
              <Button
                key="delete"
                type="text"
                icon={<DeleteOutlined />}
                size="small"
                danger
                onClick={() => handleDelete(agent.id)}
              />,
            ].filter(Boolean)}
          >
            <List.Item.Meta
              avatar={<RobotOutlined style={{ fontSize: 20, color: 'var(--accent-warm)' }} />}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="cn-sans" style={{ fontSize: 14, color: 'var(--ink)' }}>{agent.name}</span>
                  {activeAgentId === agent.id && (
                    <Tag color="success" style={{ fontSize: 11, margin: 0 }}>当前使用</Tag>
                  )}
                </div>
              }
              description={
                <div>
                  <Text style={{ fontSize: 12, color: 'var(--ink-muted)' }}>{agent.description}</Text>
                  <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    <Tag style={{ fontSize: 11, margin: 0 }}>{agent.model_id}</Tag>
                    <Tag style={{ fontSize: 11, margin: 0 }}>T={agent.temperature}</Tag>
                    {agent.tools.map((t) => (
                      <Tag key={t} style={{ fontSize: 11, margin: 0 }}>{t}</Tag>
                    ))}
                  </div>
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
