import { useState, useEffect, useMemo } from 'react';
import { Modal, Input, Button, List, Typography, message, Slider, Switch, Select, Tag, Tabs, InputNumber } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, RobotOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { fetchMcpTools, fetchAvailableModels, fetchSkills, updateAgentSkills } from '@/api/client';
import type { AgentConfig, AvailableModel, Skill, AgentSkillBinding } from '@/types';

const { Text } = Typography;
const { TextArea } = Input;
const { Option } = Select;

interface Props {
  open: boolean;
  onClose: () => void;
}

const defaultSystemPrompt = '你是一个专业的AI助手，擅长分析问题和提供详细的解决方案。请根据用户的需求，给出准确、有用的回答。';

interface FormState {
  user_id: string;
  model_id: string;
  name: string;
  description: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  tools: string[];
  skills: AgentSkillBinding[];
}

export default function AgentManageModal({ open, onClose }: Props) {
  const { agentConfigs, activeAgentId, addAgent, removeAgent, updateAgent, setActiveAgent } = useStore();
  const [activeTab, setActiveTab] = useState('basic');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [availableTools, setAvailableTools] = useState<string[]>([
    'web_search', 'code_interpreter', 'file_reader', 'image_generator', 'data_analyzer',
  ]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [skillOptions, setSkillOptions] = useState<Skill[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState>({
    user_id: '',
    model_id: '',
    name: '',
    description: '',
    system_prompt: defaultSystemPrompt,
    temperature: 0.7,
    max_tokens: 4096,
    tools: [],
    skills: [],
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
          setForm((f) => {
            if (models.length > 0 && !models.some(m => m.key === f.model_id)) {
              return { ...f, model_id: models[0].key };
            }
            return f;
          });
        })
        .catch(() => {});
      loadSkills();
    }
  }, [open]);

  const loadSkills = async () => {
    setLoadingSkills(true);
    try {
      const result = await fetchSkills({ status: 'published', size: 1000 });
      setSkillOptions(result.skills || []);
    } catch {
      // 失败时回退到 store 中已加载的 skills
      const storeSkills = useStore.getState().skills;
      setSkillOptions(storeSkills);
    } finally {
      setLoadingSkills(false);
    }
  };

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
      skills: [],
    });
    setEditingId(null);
    setActiveTab('basic');
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      message.warning('请填写Agent名称');
      return;
    }
    setSaving(true);
    try {
      const { skills, ...agentPayload } = form;
      let agentId: string | undefined;
      if (editingId) {
        await updateAgent(editingId, agentPayload);
        agentId = editingId;
      } else {
        const created = await addAgent(agentPayload);
        agentId = created.agent_code || created.id;
      }
      if (agentId) {
        await updateAgentSkills(agentId, skills);
        await useStore.getState().updateAgentSkills(agentId, skills);
      }
      message.success(editingId ? 'Agent已更新' : 'Agent已创建');
      resetForm();
    } catch (err: unknown) {
      message.error(`保存失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
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
      skills: agent.skills || [],
    });
    setActiveTab('basic');
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

  const selectedSkillIds = useMemo(() => form.skills.map((s) => s.skill_id), [form.skills]);

  const handleSkillSelect = (skillIds: number[]) => {
    const newBindings = skillIds.map((skillId) => {
      const existing = form.skills.find((s) => s.skill_id === skillId);
      if (existing) return existing;
      const skill = skillOptions.find((s) => s.id === skillId);
      return {
        skill_id: skillId,
        bound_version: skill?.current_version || '',
        binding_type: 'optional' as const,
        priority: 0,
        config_override: {},
        enabled: true,
      };
    });
    setForm((f) => ({ ...f, skills: newBindings }));
  };

  const updateBinding = (skillId: number, updates: Partial<AgentSkillBinding>) => {
    setForm((f) => ({
      ...f,
      skills: f.skills.map((b) => (b.skill_id === skillId ? { ...b, ...updates } : b)),
    }));
  };

  const removeBinding = (skillId: number) => {
    setForm((f) => ({
      ...f,
      skills: f.skills.filter((b) => b.skill_id !== skillId),
    }));
  };

  const parseConfigOverride = (value: string): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(value);
      return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return null;
    }
  };

  const basicTab = (
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
    </div>
  );

  const skillsTab = (
    <div style={{ minHeight: 240 }}>
      <div style={{ marginBottom: 16 }}>
        <Text style={{ fontSize: 12, color: 'var(--ink-muted)', display: 'block', marginBottom: 4 }}>
          选择要挂载的 Skill（仅显示已发布状态）
        </Text>
        <Select
          mode="multiple"
          placeholder="选择 Skill"
          value={selectedSkillIds}
          onChange={handleSkillSelect}
          style={{ width: '100%' }}
          loading={loadingSkills}
          optionFilterProp="label"
        >
          {skillOptions.map((skill) => (
            <Option key={skill.id} value={skill.id} label={skill.skill_name}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>{skill.skill_name}</span>
                <Tag>v{skill.current_version}</Tag>
                <Tag color="default">{skill.skill_type}</Tag>
              </div>
            </Option>
          ))}
        </Select>
      </div>

      {form.skills.length === 0 ? (
        <Text type="secondary" style={{ fontSize: 13 }}>尚未选择任何 Skill</Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {form.skills.map((binding) => {
            const skill = skillOptions.find((s) => s.id === binding.skill_id);
            return (
              <div
                key={binding.skill_id}
                style={{
                  border: '1px solid var(--paper-dark)',
                  borderRadius: 8,
                  padding: 12,
                  background: 'rgba(201,168,124,0.04)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <Text strong style={{ fontSize: 13 }}>
                    {skill?.skill_name || `Skill #${binding.skill_id}`}
                  </Text>
                  <Button type="text" danger size="small" onClick={() => removeBinding(binding.skill_id)}>
                    移除
                  </Button>
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>绑定类型</Text>
                    <Select
                      size="small"
                      value={binding.binding_type}
                      onChange={(v) => updateBinding(binding.skill_id, { binding_type: v })}
                      style={{ width: 100 }}
                    >
                      <Option value="optional">可选</Option>
                      <Option value="required">必选</Option>
                    </Select>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>优先级</Text>
                    <InputNumber
                      size="small"
                      value={binding.priority}
                      onChange={(v) => updateBinding(binding.skill_id, { priority: v || 0 })}
                      style={{ width: 72 }}
                    />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Text style={{ fontSize: 12, color: 'var(--ink-muted)', whiteSpace: 'nowrap' }}>启用</Text>
                    <Switch
                      size="small"
                      checked={binding.enabled}
                      onChange={(v) => updateBinding(binding.skill_id, { enabled: v })}
                    />
                  </div>
                </div>
                <div style={{ marginTop: 8 }}>
                  <Text style={{ fontSize: 12, color: 'var(--ink-muted)', display: 'block', marginBottom: 4 }}>
                    配置覆盖（JSON）
                  </Text>
                  <TextArea
                    size="small"
                    rows={2}
                    value={binding.config_override ? JSON.stringify(binding.config_override, null, 2) : '{}'}
                    onChange={(e) => {
                      const parsed = parseConfigOverride(e.target.value);
                      if (parsed) {
                        updateBinding(binding.skill_id, { config_override: parsed });
                      }
                    }}
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  return (
    <Modal
      open={open}
      onCancel={() => { resetForm(); onClose(); }}
      title={<span className="cn-sans" style={{ fontSize: 16, letterSpacing: '0.04em' }}>Agent管理</span>}
      footer={null}
      width={720}
      bodyStyle={{ padding: '20px 24px', maxHeight: '70vh', overflow: 'auto' }}
    >
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        { key: 'basic', label: '基本信息', children: basicTab },
        { key: 'skills', label: `Skill 绑定 (${form.skills.length})`, children: skillsTab },
      ]} />

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginBottom: 24 }}>
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
          loading={saving}
          style={{ background: 'var(--ink)', borderColor: 'var(--ink)' }}
        >
          {editingId ? '保存' : '创建Agent'}
        </Button>
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
                    {(agent.skills || []).filter((s) => s.enabled).map((s) => {
                      const skill = skillOptions.find((opt) => opt.id === s.skill_id);
                      return (
                        <Tag key={s.skill_id} color="processing" style={{ fontSize: 11, margin: 0 }}>
                          {skill?.skill_name || `Skill #${s.skill_id}`}
                        </Tag>
                      );
                    })}
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
