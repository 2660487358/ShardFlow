import { useState } from 'react';
import { Modal, Input, Button, List, Typography, message, Select, InputNumber, Tag } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import { verifyCustomModel } from '@/api/client';
import type { CustomModel } from '@/types';

const { Text } = Typography;
const { Option } = Select;

interface Props {
  open: boolean;
  onClose: () => void;
}

const CAPABILITY_OPTIONS = [
  { label: 'Chat', value: 'chat' },
  { label: 'Embedding', value: 'embedding' },
  { label: 'Vision', value: 'vision' },
  { label: 'Reasoning', value: 'reasoning' },
  { label: 'Function Calling', value: 'function_calling' },
];

export default function CustomModelModal({ open, onClose }: Props) {
  const { customModels, addCustomModel, removeCustomModel, updateCustomModel } = useStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    provider: '',
    base_url: '',
    model: '',
    api_key_id: '',
    capabilities: [] as string[],
    context_window: 4096,
    enabled: true,
  });

  const resetForm = () => {
    setForm({ name: '', provider: '', base_url: '', model: '', api_key_id: '', capabilities: [], context_window: 4096, enabled: true });
    setEditingId(null);
  };

  const handleSubmit = () => {
    if (!form.name.trim() || !form.model.trim()) {
      message.warning('请填写名称和模型');
      return;
    }
    if (editingId) {
      updateCustomModel(editingId, form);
    } else {
      addCustomModel(form);
    }
    resetForm();
  };

  const handleEdit = (model: CustomModel) => {
    setEditingId(model.id);
    setForm({
      name: model.name,
      provider: model.provider,
      base_url: model.base_url || '',
      model: model.model,
      api_key_id: '', // don't show existing key
      capabilities: typeof model.capabilities === 'string'
        ? JSON.parse(model.capabilities as string)
        : (Array.isArray(model.capabilities) ? model.capabilities : []),
      context_window: model.context_window || 4096,
      enabled: model.enabled,
    });
  };

  const handleDelete = (id: string) => {
    removeCustomModel(id);
    if (editingId === id) resetForm();
  };

  const handleVerify = async (id: string) => {
    setVerifying(id);
    try {
      const result = await verifyCustomModel(id);
      if (result.success) {
        message.success(`连通性验证成功 (${result.latency_ms}ms)`);
        updateCustomModel(id, { is_verified: true });
      } else {
        message.error(`验证失败: ${result.error || '未知错误'}`);
        updateCustomModel(id, { is_verified: false });
      }
    } catch {
      message.error('验证请求失败');
    } finally {
      setVerifying(null);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={() => { resetForm(); onClose(); }}
      title={<span className="cn-sans" style={{ fontSize: 16, letterSpacing: '0.04em' }}>自定义模型</span>}
      footer={null}
      width={560}
      bodyStyle={{ padding: '20px 24px' }}
    >
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Input
            placeholder="显示名称"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            style={{ flex: 1, fontFamily: 'var(--font-sans)' }}
          />
          <Select
            placeholder="厂商"
            value={form.provider || undefined}
            onChange={(v) => setForm((f) => ({ ...f, provider: v }))}
            style={{ flex: 1 }}
            allowClear
          >
            <Option value="openai">OpenAI</Option>
            <Option value="deepseek">DeepSeek</Option>
            <Option value="anthropic">Anthropic</Option>
            <Option value="azure">Azure</Option>
            <Option value="other">其他</Option>
          </Select>
        </div>
        <div style={{ marginBottom: 12 }}>
          <Input
            placeholder="API 地址 (如 https://api.openai.com/v1)"
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
            style={{ fontFamily: 'var(--font-sans)' }}
          />
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Input
            placeholder="模型 ID (如 gpt-4o)"
            value={form.model}
            onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            style={{ flex: 1, fontFamily: 'var(--font-sans)' }}
          />
          <Input.Password
            placeholder="API Key"
            value={form.api_key_id}
            onChange={(e) => setForm((f) => ({ ...f, api_key_id: e.target.value }))}
            style={{ flex: 1, fontFamily: 'var(--font-sans)' }}
          />
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <div style={{ flex: 1 }}>
            <Text style={{ fontSize: 12, color: 'var(--ink-muted)', display: 'block', marginBottom: 4 }}>能力标签</Text>
            <Select
              mode="multiple"
              placeholder="选择能力"
              value={form.capabilities}
              onChange={(v) => setForm((f) => ({ ...f, capabilities: v }))}
              style={{ width: '100%' }}
            >
              {CAPABILITY_OPTIONS.map((opt) => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </div>
          <div style={{ width: 140 }}>
            <Text style={{ fontSize: 12, color: 'var(--ink-muted)', display: 'block', marginBottom: 4 }}>上下文窗口</Text>
            <InputNumber
              min={1024}
              max={1000000}
              step={1024}
              value={form.context_window}
              onChange={(v) => setForm((f) => ({ ...f, context_window: v || 4096 }))}
              style={{ width: '100%' }}
            />
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
            {editingId ? '保存' : '添加'}
          </Button>
        </div>
      </div>

      <div className="hand-line" style={{ margin: '0 0 16px' }} />

      <List
        dataSource={customModels}
        locale={{ emptyText: <Text className="cn-tag" style={{ color: 'var(--ink-muted)' }}>暂无自定义模型</Text> }}
        renderItem={(model) => (
          <List.Item
            style={{ padding: '8px 0', borderBottom: '1px solid var(--paper-dark)' }}
            actions={[
              <Button
                key="verify"
                type="text"
                icon={model.is_verified ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                size="small"
                loading={verifying === model.id}
                onClick={() => handleVerify(model.id)}
                style={{ color: model.is_verified ? 'var(--success)' : 'var(--ink-faint)' }}
              />,
              <Button
                key="edit"
                type="text"
                icon={<EditOutlined />}
                size="small"
                onClick={() => handleEdit(model)}
                style={{ color: 'var(--ink-faint)' }}
              />,
              <Button
                key="delete"
                type="text"
                icon={<DeleteOutlined />}
                size="small"
                danger
                onClick={() => handleDelete(model.id)}
              />,
            ]}
          >
            <List.Item.Meta
              avatar={<RobotOutlined style={{ fontSize: 18, color: 'var(--accent-warm)' }} />}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="cn-sans" style={{ fontSize: 14, color: 'var(--ink)' }}>{model.name}</span>
                  <Tag style={{ fontSize: 11, margin: 0 }}>API: {model.api_key_id ? '已配置' : '未配置'}</Tag>
                  {model.is_verified && (
                    <Tag color="success" style={{ fontSize: 11, margin: 0 }}>已验证</Tag>
                  )}
                </div>
              }
              description={
                <Text style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
                  {model.model} · {model.provider || 'default'}
                  {model.base_url ? ` · ${model.base_url}` : ''}
                </Text>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
