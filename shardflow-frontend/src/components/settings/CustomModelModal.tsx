import { useState } from 'react';
import { Modal, Input, Button, List, Typography, message } from 'antd';
import { DeleteOutlined, EditOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons';
import { useStore } from '@/store';
import type { CustomModel } from '@/types';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CustomModelModal({ open, onClose }: Props) {
  const { customModels, addCustomModel, removeCustomModel, updateCustomModel } = useStore();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    provider: '',
    model: '',
    api_key_id: '',
    enabled: true,
  });

  const resetForm = () => {
    setForm({ name: '', provider: '', model: '', api_key_id: '', enabled: true });
    setEditingId(null);
  };

  const handleSubmit = () => {
    if (!form.name.trim() || !form.model.trim()) {
      message.warning('请填写名称和模型');
      return;
    }
    if (editingId) {
      updateCustomModel(editingId, form);
      message.success('模型已更新');
    } else {
      addCustomModel(form);
      message.success('模型已添加');
    }
    resetForm();
  };

  const handleEdit = (model: CustomModel) => {
    setEditingId(model.id);
    setForm({
      name: model.name,
      provider: model.provider,
      model: model.model,
      api_key_id: model.api_key_id,
      enabled: model.enabled,
    });
  };

  const handleDelete = (id: string) => {
    removeCustomModel(id);
    if (editingId === id) resetForm();
    message.success('模型已删除');
  };

  return (
    <Modal
      open={open}
      onCancel={() => { resetForm(); onClose(); }}
      title={<span className="cn-sans" style={{ fontSize: 16, letterSpacing: '0.04em' }}>自定义模型</span>}
      footer={null}
      width={520}
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
          <Input
            placeholder="Provider"
            value={form.provider}
            onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
            style={{ flex: 1, fontFamily: 'var(--font-sans)' }}
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
              title={<span className="cn-sans" style={{ fontSize: 14, color: 'var(--ink)' }}>{model.name}</span>}
              description={
                <Text style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
                  {model.model} · {model.provider || 'default'}
                </Text>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
