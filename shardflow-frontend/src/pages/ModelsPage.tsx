import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Button, Card, Tag, Typography, message, Empty, Input, Modal, Form, Popconfirm, Tooltip,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, EditOutlined, RobotOutlined, SearchOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import { useStore } from '@/store';
import { verifyCustomModel } from '@/api/client';
import type { CustomModel } from '@/types';

const { Title, Text, Paragraph } = Typography;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function ModelsPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const { customModels, addCustomModel, removeCustomModel, updateCustomModel } = useStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<CustomModel | null>(null);
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState('');
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState<string | null>(null);

  const filteredModels = customModels.filter((m) => {
    if (!searchText.trim()) return true;
    const q = searchText.toLowerCase();
    return m.name.toLowerCase().includes(q) || m.model.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q);
  });

  const handleAdd = (values: { name: string; provider: string; base_url: string; model: string; api_key_id: string }) => {
    setSaving(true);
    addCustomModel({ ...values, capabilities: [], context_window: 4096, enabled: true });
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
  };

  const handleEdit = (values: { name: string; provider: string; base_url: string; model: string; api_key_id: string }) => {
    if (!editingModel) return;
    setSaving(true);
    updateCustomModel(editingModel.id, { ...values, enabled: editingModel.enabled });
    setEditingModel(null);
    setModalOpen(false);
    form.resetFields();
    setSaving(false);
  };

  const handleDelete = (id: string) => {
    removeCustomModel(id);
  };

  const handleVerify = async (model: CustomModel) => {
    setVerifying(model.id);
    try {
      const result = await verifyCustomModel(model.id);
      if (result.success) {
        message.success(`连通性验证成功 (${result.latency_ms}ms)`);
        updateCustomModel(model.id, { is_verified: true });
      } else {
        message.error(`验证失败: ${result.error || '未知错误'}`);
        updateCustomModel(model.id, { is_verified: false });
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        message.error('登录已过期，请重新登录');
        onLoginRequired();
      } else {
        message.error('验证请求失败，请检查后端服务');
      }
    } finally {
      setVerifying(null);
    }
  };

  const openAddModal = () => {
    setEditingModel(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEditModal = (model: CustomModel) => {
    setEditingModel(model);
    form.setFieldsValue({
      name: model.name,
      provider: model.provider,
      base_url: model.base_url || '',
      model: model.model,
      api_key_id: '', // don't show existing key
    });
    setModalOpen(true);
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用模型功能</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>模型</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>管理你的自定义模型配置</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddModal} className="cn-sans">
            新建模型
          </Button>
        </div>

        {/* 搜索栏 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <Input
            prefix={<SearchOutlined style={{ color: 'var(--ink-faint)' }} />}
            placeholder="搜索模型..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            style={{ maxWidth: 320 }}
          />
        </div>

        {/* 模型列表 */}
        {filteredModels.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的模型' : '还没有模型，点击上方按钮创建'} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
            {filteredModels.map((model) => (
              <Card
                key={model.id}
                hoverable
                style={{
                  background: 'rgba(255,255,255,0.6)',
                  border: '1px solid var(--paper-dark)',
                }}
                actions={[
                  <Button
                    key="edit"
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => openEditModal(model)}
                  />,
                  <Tooltip key="verify" title={model.is_verified ? '已验证通过，点击重新验证' : '验证模型 API 连通性'}>
                    <Button
                      type="text"
                      icon={<CheckCircleOutlined />}
                      loading={verifying === model.id}
                      onClick={() => handleVerify(model)}
                      style={{ color: model.is_verified ? 'var(--accent-warm)' : 'var(--ink-faint)' }}
                    />
                  </Tooltip>,
                  <Popconfirm
                    key="delete"
                    title="确定删除此模型？"
                    description={`确定要删除模型「${model.name}」吗？`}
                    onConfirm={() => handleDelete(model.id)}
                  >
                    <Button type="text" icon={<DeleteOutlined />} danger />
                  </Popconfirm>,
                ]}
              >
                <Card.Meta
                  avatar={
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: model.enabled ? 'rgba(201,168,124,0.15)' : 'rgba(255,255,255,0.5)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: model.enabled ? '1px solid var(--accent)' : '1px solid var(--paper-dark)',
                    }}>
                      <RobotOutlined style={{ fontSize: 20, color: model.enabled ? 'var(--accent-warm)' : '#c9a87c' }} />
                    </div>
                  }
                  title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{model.name}</span>
                      <Tag color={model.enabled ? 'success' : 'default'} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                        {model.enabled ? '已启用' : '已停用'}
                      </Tag>
                    </div>
                  }
                  description={
                    <>
                      <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8, minHeight: 44 }}>
                        {model.model} · {model.provider || 'default'}
                        {model.base_url ? ` · ${model.base_url}` : ''}
                      </Paragraph>
                      <div style={{ display: 'flex', gap: 16 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          API: {model.api_key_id ? '已配置' : '未配置'}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
                          {new Date(model.created_at).toLocaleDateString('zh-CN')}
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

      {/* 新建/编辑模型 Modal */}
      <Modal
        title={editingModel ? '编辑模型' : '新建模型'}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingModel(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText={editingModel ? '保存' : '创建'}
        cancelText="取消"
        confirmLoading={saving}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={editingModel ? handleEdit : handleAdd}
        >
          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: '请输入显示名称' }]}
          >
            <Input placeholder="显示名称" />
          </Form.Item>
          <Form.Item
            name="provider"
            label="Provider"
          >
            <Input placeholder="Provider（如 openai、deepseek）" />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API 地址"
            rules={[
              { type: 'url', message: '请输入有效的 URL 地址' },
            ]}
          >
            <Input placeholder="API 地址（如 https://api.openai.com/v1）" />
          </Form.Item>
          <Form.Item
            name="model"
            label="模型 ID"
            rules={[{ required: true, message: '请输入模型 ID' }]}
          >
            <Input placeholder="模型 ID（如 gpt-4o）" />
          </Form.Item>
          <Form.Item
            name="api_key_id"
            label="API Key"
          >
            <Input.Password placeholder="API Key" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
