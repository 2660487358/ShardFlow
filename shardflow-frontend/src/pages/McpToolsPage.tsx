import { useState, useEffect, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Typography, Table, Button, Input, Select, Tag, Badge, Space,
  Modal, Drawer, Form, InputNumber, Popconfirm, message, Tabs,
  Tooltip, Descriptions, Alert,
} from 'antd';
import {
  PlusOutlined, SearchOutlined, EditOutlined,
  CheckCircleOutlined, StopOutlined, PlayCircleOutlined,
  DeleteOutlined, HeartOutlined, EyeOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { McpToolSummary, McpTool, McpToolRegisterRequest, McpHealthCheckResult, McpVersionResult } from '@/types';
import {
  fetchMcpToolList, fetchMcpToolDetail, registerMcpTool,
  updateMcpTool, deleteMcpTool, changeMcpToolStatus,
  checkMcpToolHealth, fetchMcpToolVersions, rollbackMcpToolVersion,
} from '@/api/client';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'DRAFT', label: '草稿' },
  { value: 'ACTIVE', label: '已激活' },
  { value: 'INACTIVE', label: '已停用' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: '全部分类' },
  { value: 'SEARCH', label: '搜索' },
  { value: 'STORAGE', label: '存储' },
  { value: 'COMPUTE', label: '计算' },
  { value: 'COMMUNICATION', label: '通信' },
  { value: 'DATA_PROCESSING', label: '数据处理' },
  { value: 'OTHER', label: '其他' },
];

const RISK_LEVEL_OPTIONS = [
  { value: 'LOW', label: '低' },
  { value: 'MEDIUM', label: '中' },
  { value: 'HIGH', label: '高' },
  { value: 'CRITICAL', label: '严重' },
];

const TRANSPORT_OPTIONS = [
  { value: 'stdio', label: 'stdio' },
  { value: 'sse', label: 'SSE' },
  { value: 'streamable-http', label: 'Streamable HTTP' },
];

const AUTH_TYPE_OPTIONS = [
  { value: 'NONE', label: '无认证' },
  { value: 'BEARER', label: 'Bearer Token' },
  { value: 'API_KEY', label: 'API Key' },
  { value: 'OAUTH2', label: 'OAuth 2.0' },
];

function statusTag(status: string) {
  const map: Record<string, { color: string; label: string }> = {
    DRAFT: { color: 'default', label: '草稿' },
    ACTIVE: { color: 'success', label: '已激活' },
    INACTIVE: { color: 'warning', label: '已停用' },
  };
  const info = map[status] || { color: 'default', label: status };
  return <Tag color={info.color}>{info.label}</Tag>;
}

function healthBadge(status: string) {
  const map: Record<string, { status: 'success' | 'error' | 'default'; text: string }> = {
    HEALTHY: { status: 'success', text: '健康' },
    UNHEALTHY: { status: 'error', text: '异常' },
    UNKNOWN: { status: 'default', text: '未知' },
  };
  const info = map[status] || { status: 'default' as const, text: status };
  return <Badge status={info.status} text={info.text} />;
}

function getNextStatus(current: string): { status: string; label: string; icon: React.ReactNode } | null {
  if (current === 'DRAFT') return { status: 'ACTIVE', label: '激活', icon: <PlayCircleOutlined /> };
  if (current === 'ACTIVE') return { status: 'INACTIVE', label: '停用', icon: <StopOutlined /> };
  if (current === 'INACTIVE') return { status: 'ACTIVE', label: '激活', icon: <PlayCircleOutlined /> };
  return null;
}

function getStatusTransitionHint(current: string): string {
  if (current === 'DRAFT') return '草稿 → 已激活：工具将可被 Agent 调用';
  if (current === 'ACTIVE') return '已激活 → 已停用：工具将暂停服务';
  if (current === 'INACTIVE') return '已停用 → 已激活：工具将恢复服务';
  return '';
}

// ── Tool Register / Edit Form ──

interface ToolFormProps {
  open: boolean;
  editTool?: McpTool | null;
  onClose: () => void;
  onSuccess: () => void;
}

function ToolFormModal({ open, editTool, onClose, onSuccess }: ToolFormProps) {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const isEdit = !!editTool;

  useEffect(() => {
    if (open && editTool) {
      form.setFieldsValue({
        toolName: editTool.toolName,
        description: editTool.description,
        category: editTool.category || undefined,
        tags: editTool.tags?.join(', '),
        mcpServerUrl: editTool.mcpServerUrl,
        transport: editTool.transport || undefined,
        healthCheckUrl: editTool.healthCheckUrl,
        version: editTool.version,
        timeoutSeconds: editTool.timeoutSeconds,
        retryCount: editTool.retryCount,
        riskLevel: editTool.riskLevel || undefined,
        permissions: editTool.permissions?.join(', '),
        ownerTeam: editTool.ownerTeam,
        authConfigType: editTool.authConfigType || 'NONE',
        inputSchema: editTool.inputSchema ? JSON.stringify(editTool.inputSchema, null, 2) : '',
        outputSchema: editTool.outputSchema ? JSON.stringify(editTool.outputSchema, null, 2) : '',
      });
    } else if (open) {
      form.resetFields();
      form.setFieldsValue({ authConfigType: 'NONE', transport: 'stdio', timeoutSeconds: 30, retryCount: 3 });
    }
  }, [open, editTool, form]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);

      let inputSchema: Record<string, unknown> | undefined;
      let outputSchema: Record<string, unknown> | undefined;
      try {
        if (values.inputSchema?.trim()) inputSchema = JSON.parse(values.inputSchema);
      } catch { message.error('inputSchema JSON 格式错误'); setSubmitting(false); return; }
      try {
        if (values.outputSchema?.trim()) outputSchema = JSON.parse(values.outputSchema);
      } catch { message.error('outputSchema JSON 格式错误'); setSubmitting(false); return; }

      const request: McpToolRegisterRequest = {
        toolName: values.toolName,
        description: values.description,
        category: values.category,
        tags: values.tags ? values.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
        mcpServerUrl: values.mcpServerUrl,
        transport: values.transport,
        healthCheckUrl: values.healthCheckUrl,
        inputSchema,
        outputSchema,
        permissions: values.permissions ? values.permissions.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
        riskLevel: values.riskLevel,
        version: values.version,
        timeoutSeconds: values.timeoutSeconds,
        retryCount: values.retryCount,
        ownerTeam: values.ownerTeam,
        authConfig: values.authConfigType && values.authConfigType !== 'NONE' ? {
          type: values.authConfigType,
          tokenKey: values.authTokenKey,
          keyName: values.authKeyName,
          keyValueEnv: values.authKeyValueEnv,
          clientIdEnv: values.authClientIdEnv,
          clientSecretEnv: values.authClientSecretEnv,
          tokenUrl: values.authTokenUrl,
        } : undefined,
      };

      if (isEdit && editTool) {
        await updateMcpTool(editTool.toolId, request);
        message.success('工具更新成功');
      } else {
        await registerMcpTool(request);
        message.success('工具注册成功');
      }
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        message.error(`操作失败: ${err.message}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const authConfigType = Form.useWatch('authConfigType', form);

  return (
    <Modal
      title={isEdit ? '编辑工具' : '注册新工具'}
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      okText={isEdit ? '保存' : '注册'}
      confirmLoading={submitting}
      width={720}
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ maxHeight: '65vh', overflowY: 'auto', paddingRight: 8 }}>
        <Form.Item name="toolName" label="工具名称" rules={[{ required: true, message: '请输入工具名称' }]}>
          <Input placeholder="如: web_search" disabled={isEdit} />
        </Form.Item>
        <Form.Item name="description" label="描述" rules={[{ required: true, message: '请输入描述' }]}>
          <TextArea rows={2} placeholder="工具功能描述" />
        </Form.Item>
        <Space style={{ width: '100%' }} size="middle">
          <Form.Item name="category" label="分类" style={{ width: 200 }}>
            <Select options={CATEGORY_OPTIONS.filter(o => o.value)} placeholder="选择分类" allowClear />
          </Form.Item>
          <Form.Item name="version" label="版本" rules={[
            { required: true, message: '请输入版本号' },
            { pattern: /^\d+\.\d+\.\d+$/, message: '格式: MAJOR.MINOR.PATCH' },
          ]} style={{ width: 160 }}>
            <Input placeholder="1.0.0" />
          </Form.Item>
          <Form.Item name="riskLevel" label="风险等级" style={{ width: 140 }}>
            <Select options={RISK_LEVEL_OPTIONS} placeholder="选择等级" allowClear />
          </Form.Item>
        </Space>
        <Form.Item name="tags" label="标签（逗号分隔）">
          <Input placeholder="search, web, api" />
        </Form.Item>
        <Space style={{ width: '100%' }} size="middle">
          <Form.Item name="mcpServerUrl" label="MCP 服务地址" style={{ flex: 1 }}>
            <Input placeholder="http://localhost:3001/mcp" />
          </Form.Item>
          <Form.Item name="transport" label="传输协议" style={{ width: 180 }}>
            <Select options={TRANSPORT_OPTIONS} />
          </Form.Item>
        </Space>
        <Form.Item name="healthCheckUrl" label="健康检查地址">
          <Input placeholder="http://localhost:3001/health" />
        </Form.Item>
        <Space style={{ width: '100%' }} size="middle">
          <Form.Item name="timeoutSeconds" label="超时（秒）">
            <InputNumber min={1} max={300} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="retryCount" label="重试次数">
            <InputNumber min={0} max={10} style={{ width: 120 }} />
          </Form.Item>
        </Space>
        <Form.Item name="permissions" label="权限（逗号分隔）">
          <Input placeholder="read, write" />
        </Form.Item>
        <Form.Item name="ownerTeam" label="所属团队">
          <Input placeholder="backend-team" />
        </Form.Item>

        <div style={{ borderTop: '1px solid var(--colorBorderSecondary, #e8e2d6)', paddingTop: 16, marginTop: 8 }}>
          <Text strong style={{ marginBottom: 12, display: 'block' }}>认证配置</Text>
          <Form.Item name="authConfigType" label="认证类型">
            <Select options={AUTH_TYPE_OPTIONS} />
          </Form.Item>
          {authConfigType === 'BEARER' && (
            <Form.Item name="authTokenKey" label="Token Key">
              <Input placeholder="环境变量名，如: MCP_AUTH_TOKEN" />
            </Form.Item>
          )}
          {authConfigType === 'API_KEY' && (
            <Space style={{ width: '100%' }} size="middle">
              <Form.Item name="authKeyName" label="Key Name" style={{ flex: 1 }}>
                <Input placeholder="如: X-API-Key" />
              </Form.Item>
              <Form.Item name="authKeyValueEnv" label="Key Value Env" style={{ flex: 1 }}>
                <Input placeholder="环境变量名" />
              </Form.Item>
            </Space>
          )}
          {authConfigType === 'OAUTH2' && (
            <Space style={{ width: '100%' }} size="middle" direction="vertical">
              <Form.Item name="authClientIdEnv" label="Client ID Env" style={{ marginBottom: 8 }}>
                <Input placeholder="环境变量名" />
              </Form.Item>
              <Form.Item name="authClientSecretEnv" label="Client Secret Env" style={{ marginBottom: 8 }}>
                <Input placeholder="环境变量名" />
              </Form.Item>
              <Form.Item name="authTokenUrl" label="Token URL" style={{ marginBottom: 0 }}>
                <Input placeholder="https://auth.example.com/token" />
              </Form.Item>
            </Space>
          )}
        </div>

        <div style={{ borderTop: '1px solid var(--colorBorderSecondary, #e8e2d6)', paddingTop: 16, marginTop: 16 }}>
          <Text strong style={{ marginBottom: 12, display: 'block' }}>Schema 定义</Text>
          <Form.Item name="inputSchema" label="Input Schema (JSON)" extra="留空则不设置">
            <TextArea rows={6} placeholder='{"type":"object","properties":{}}' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item name="outputSchema" label="Output Schema (JSON)" extra="留空则不设置">
            <TextArea rows={6} placeholder='{"type":"object","properties":{}}' style={{ fontFamily: 'monospace' }} />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}

// ── Tool Detail Drawer ──

interface DetailDrawerProps {
  open: boolean;
  toolId: string | null;
  onClose: () => void;
  onEdit: (tool: McpTool) => void;
}

function DetailDrawer({ open, toolId, onClose, onEdit }: DetailDrawerProps) {
  const [tool, setTool] = useState<McpTool | null>(null);
  const [loading, setLoading] = useState(false);
  const [versions, setVersions] = useState<McpVersionResult | null>(null);
  const [healthResult, setHealthResult] = useState<McpHealthCheckResult | null>(null);
  const [healthChecking, setHealthChecking] = useState(false);
  const [activeTab, setActiveTab] = useState('basic');

  const loadDetail = useCallback(async () => {
    if (!toolId) return;
    setLoading(true);
    try {
      const detail = await fetchMcpToolDetail(toolId);
      setTool(detail);
    } catch {
      message.error('获取工具详情失败');
    } finally {
      setLoading(false);
    }
  }, [toolId]);

  const loadVersions = useCallback(async () => {
    if (!toolId) return;
    try {
      const result = await fetchMcpToolVersions(toolId);
      setVersions(result);
    } catch { /* ignore */ }
  }, [toolId]);

  useEffect(() => {
    if (open && toolId) {
      loadDetail();
      setVersions(null);
      setHealthResult(null);
      setActiveTab('basic');
    }
  }, [open, toolId, loadDetail]);

  const handleHealthCheck = async () => {
    if (!toolId) return;
    setHealthChecking(true);
    try {
      const result = await checkMcpToolHealth(toolId);
      setHealthResult(result);
      message.success(`健康检查完成: ${result.healthStatus}`);
      loadDetail();
    } catch (err: unknown) {
      if (err instanceof Error) message.error(`健康检查失败: ${err.message}`);
    } finally {
      setHealthChecking(false);
    }
  };

  const handleRollback = async (targetVersion: string) => {
    if (!toolId) return;
    try {
      await rollbackMcpToolVersion(toolId, targetVersion);
      message.success(`已回滚至 ${targetVersion}`);
      loadDetail();
      loadVersions();
    } catch (err: unknown) {
      if (err instanceof Error) message.error(`回滚失败: ${err.message}`);
    }
  };

  return (
    <Drawer
      title={tool ? tool.toolName : '工具详情'}
      open={open}
      onClose={onClose}
      width={640}
      loading={loading}
      extra={tool && (
        <Button type="primary" icon={<EditOutlined />} onClick={() => onEdit(tool)}>
          编辑
        </Button>
      )}
    >
      {tool && (
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
          {
            key: 'basic',
            label: '基本信息',
            children: (
              <Descriptions column={2} bordered size="small">
                <Descriptions.Item label="工具名称">{tool.toolName}</Descriptions.Item>
                <Descriptions.Item label="类型">{tool.toolType}</Descriptions.Item>
                <Descriptions.Item label="描述" span={2}>{tool.description}</Descriptions.Item>
                <Descriptions.Item label="分类">{tool.category || '-'}</Descriptions.Item>
                <Descriptions.Item label="版本">{tool.version}</Descriptions.Item>
                <Descriptions.Item label="状态">{statusTag(tool.status)}</Descriptions.Item>
                <Descriptions.Item label="健康状态">{healthBadge(tool.healthStatus)}</Descriptions.Item>
                <Descriptions.Item label="风险等级">
                  <Tag color={tool.riskLevel === 'HIGH' || tool.riskLevel === 'CRITICAL' ? 'red' : tool.riskLevel === 'MEDIUM' ? 'orange' : 'green'}>
                    {tool.riskLevel || '-'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="所属团队">{tool.ownerTeam || '-'}</Descriptions.Item>
                <Descriptions.Item label="MCP 地址" span={2}>{tool.mcpServerUrl || '-'}</Descriptions.Item>
                <Descriptions.Item label="传输协议">{tool.transport || '-'}</Descriptions.Item>
                <Descriptions.Item label="健康检查地址" span={2}>{tool.healthCheckUrl || '-'}</Descriptions.Item>
                <Descriptions.Item label="超时（秒）">{tool.timeoutSeconds}</Descriptions.Item>
                <Descriptions.Item label="重试次数">{tool.retryCount}</Descriptions.Item>
                <Descriptions.Item label="认证类型">{tool.authConfigType || 'NONE'}</Descriptions.Item>
                <Descriptions.Item label="标签" span={2}>
                  {tool.tags?.length ? tool.tags.map(t => <Tag key={t}>{t}</Tag>) : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="权限" span={2}>
                  {tool.permissions?.length ? tool.permissions.map(p => <Tag key={p} color="blue">{p}</Tag>) : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">{tool.createdAt}</Descriptions.Item>
                <Descriptions.Item label="更新时间">{tool.updatedAt}</Descriptions.Item>
                <Descriptions.Item label="上次健康检查" span={2}>{tool.lastHealthCheckAt || '-'}</Descriptions.Item>
              </Descriptions>
            ),
          },
          {
            key: 'schema',
            label: 'Schema',
            children: (
              <div>
                <Text strong>Input Schema</Text>
                <pre style={{
                  background: 'rgba(255,255,255,0.5)', padding: 12, borderRadius: 8,
                  fontSize: 12, overflow: 'auto', maxHeight: 300, border: '1px solid #e8e2d6',
                  fontFamily: 'monospace',
                }}>
                  {tool.inputSchema ? JSON.stringify(tool.inputSchema, null, 2) : '未定义'}
                </pre>
                <Text strong style={{ marginTop: 16, display: 'block' }}>Output Schema</Text>
                <pre style={{
                  background: 'rgba(255,255,255,0.5)', padding: 12, borderRadius: 8,
                  fontSize: 12, overflow: 'auto', maxHeight: 300, border: '1px solid #e8e2d6',
                  fontFamily: 'monospace',
                }}>
                  {tool.outputSchema ? JSON.stringify(tool.outputSchema, null, 2) : '未定义'}
                </pre>
              </div>
            ),
          },
          {
            key: 'versions',
            label: '版本历史',
            children: (
              <div>
                <Button size="small" onClick={loadVersions} style={{ marginBottom: 12 }}>
                  加载版本历史
                </Button>
                {versions ? (
                  versions.versions.length > 0 ? (
                    <Table
                      size="small"
                      pagination={false}
                      dataSource={versions.versions}
                      rowKey="id"
                      columns={[
                        { title: '版本', dataIndex: 'version', width: 100 },
                        { title: '描述', dataIndex: 'description', ellipsis: true },
                        { title: '状态', dataIndex: 'status', width: 80, render: (s: string) => <Tag>{s}</Tag> },
                        { title: '创建人', dataIndex: 'createdBy', width: 100 },
                        { title: '创建时间', dataIndex: 'createdAt', width: 160 },
                        {
                          title: '操作', width: 80, render: (_: unknown, record: McpVersionResult['versions'][0]) =>
                            record.version !== versions.currentVersion ? (
                              <Popconfirm title={`确认回滚至 ${record.version}?`} onConfirm={() => handleRollback(record.version)}>
                                <Button size="small" type="link">回滚</Button>
                              </Popconfirm>
                            ) : <Tag color="success">当前</Tag>,
                        },
                      ]}
                    />
                  ) : <Text type="secondary">暂无版本历史</Text>
                ) : null}
              </div>
            ),
          },
          {
            key: 'health',
            label: '健康状态',
            children: (
              <div>
                <Space style={{ marginBottom: 16 }}>
                  <Button icon={<HeartOutlined />} onClick={handleHealthCheck} loading={healthChecking}>
                    手动健康检查
                  </Button>
                </Space>
                {healthResult && (
                  <Alert
                    type={healthResult.healthStatus === 'HEALTHY' ? 'success' : healthResult.healthStatus === 'UNHEALTHY' ? 'error' : 'warning'}
                    showIcon
                    message={`健康状态: ${healthResult.healthStatus}`}
                    description={
                      <Descriptions column={1} size="small">
                        <Descriptions.Item label="消息">{healthResult.message}</Descriptions.Item>
                        <Descriptions.Item label="延迟">{healthResult.latencyMs}ms</Descriptions.Item>
                        <Descriptions.Item label="连续成功">{healthResult.consecutiveSuccesses}</Descriptions.Item>
                        <Descriptions.Item label="连续失败">{healthResult.consecutiveFailures}</Descriptions.Item>
                        <Descriptions.Item label="检查时间">{healthResult.lastHealthCheckAt}</Descriptions.Item>
                      </Descriptions>
                    }
                    style={{ marginBottom: 16 }}
                  />
                )}
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="当前状态">{healthBadge(tool.healthStatus)}</Descriptions.Item>
                  <Descriptions.Item label="上次检查">{tool.lastHealthCheckAt || '-'}</Descriptions.Item>
                </Descriptions>
              </div>
            ),
          },
        ]} />
      )}
    </Drawer>
  );
}

// ── Main Page ──

export default function McpToolsPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();

  const [tools, setTools] = useState<McpToolSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [keyword, setKeyword] = useState('');

  const [registerOpen, setRegisterOpen] = useState(false);
  const [editTool, setEditTool] = useState<McpTool | null>(null);
  const [detailToolId, setDetailToolId] = useState<string | null>(null);

  const loadTools = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try {
      const result = await fetchMcpToolList({
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        keyword: keyword || undefined,
        page,
        size,
      });
      setTools(result.tools || []);
      setTotal(result.total || 0);
    } catch {
      message.error('获取工具列表失败');
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, statusFilter, categoryFilter, keyword, page, size]);

  useEffect(() => {
    loadTools();
  }, [loadTools]);

  const handleStatusChange = async (toolId: string, currentStatus: string) => {
    const next = getNextStatus(currentStatus);
    if (!next) return;
    try {
      await changeMcpToolStatus(toolId, next.status);
      message.success(`工具已${next.label}`);
      loadTools();
    } catch (err: unknown) {
      if (err instanceof Error) message.error(`操作失败: ${err.message}`);
    }
  };

  const handleDelete = async (toolId: string) => {
    try {
      await deleteMcpTool(toolId);
      message.success('工具已删除');
      loadTools();
    } catch (err: unknown) {
      if (err instanceof Error) message.error(`删除失败: ${err.message}`);
    }
  };

  const handleHealthCheck = async (toolId: string) => {
    try {
      const result = await checkMcpToolHealth(toolId);
      message.success(`健康检查完成: ${result.healthStatus}`);
      loadTools();
    } catch (err: unknown) {
      if (err instanceof Error) message.error(`健康检查失败: ${err.message}`);
    }
  };

  const handleEditFromDetail = (tool: McpTool) => {
    setDetailToolId(null);
    setEditTool(tool);
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以使用 MCP 管理功能</Text>
      </div>
    );
  }

  const columns: ColumnsType<McpToolSummary> = [
    {
      title: '工具名称',
      dataIndex: 'toolName',
      width: 160,
      render: (name: string, record: McpToolSummary) => (
        <Button type="link" style={{ padding: 0, height: 'auto', fontWeight: 500 }} onClick={() => setDetailToolId(record.toolId)}>
          {name}
        </Button>
      ),
    },
    {
      title: '类型',
      dataIndex: 'toolType',
      width: 80,
      render: (t: string) => <Tag>{t}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 100,
      render: (c: string) => c || '-',
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 80,
      render: (v: string) => <Tag>v{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => statusTag(s),
    },
    {
      title: '健康',
      dataIndex: 'healthStatus',
      width: 90,
      render: (h: string) => healthBadge(h),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 160,
    },
    {
      title: '操作',
      width: 220,
      render: (_: unknown, record: McpToolSummary) => {
        const next = getNextStatus(record.status);
        return (
          <Space size={4}>
            <Tooltip title="查看详情">
              <Button size="small" type="text" icon={<EyeOutlined />} onClick={() => setDetailToolId(record.toolId)} />
            </Tooltip>
            <Tooltip title="编辑">
              <Button size="small" type="text" icon={<EditOutlined />} onClick={() => {
                fetchMcpToolDetail(record.toolId).then(setEditTool).catch(() => message.error('获取工具详情失败'));
              }} />
            </Tooltip>
            {next && (
              <Popconfirm
                title={
                  <div>
                    <div>确认将工具状态变更为 <b>{next.label}</b>？</div>
                    <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{getStatusTransitionHint(record.status)}</div>
                  </div>
                }
                onConfirm={() => handleStatusChange(record.toolId, record.status)}
                icon={<ExclamationCircleOutlined />}
              >
                <Tooltip title={next.label}>
                  <Button size="small" type="text" icon={next.icon} />
                </Tooltip>
              </Popconfirm>
            )}
            <Tooltip title="健康检查">
              <Button size="small" type="text" icon={<HeartOutlined />} onClick={() => handleHealthCheck(record.toolId)} />
            </Tooltip>
            <Popconfirm title="确认删除此工具？" onConfirm={() => handleDelete(record.toolId)} okButtonProps={{ danger: true }}>
              <Tooltip title="删除">
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>MCP 工具管理</Title>
            <Text type="secondary" style={{ fontSize: 13 }}>注册、管理和监控 MCP 工具</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterOpen(true)}>
            注册工具
          </Button>
        </div>

        {/* 筛选栏 */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <Select
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); }}
            options={STATUS_OPTIONS}
            style={{ width: 140 }}
          />
          <Select
            value={categoryFilter}
            onChange={(v) => { setCategoryFilter(v); setPage(1); }}
            options={CATEGORY_OPTIONS}
            style={{ width: 140 }}
          />
          <Input
            placeholder="搜索工具名称..."
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={() => { setPage(1); loadTools(); }}
            style={{ width: 240 }}
            allowClear
            onClear={() => { setKeyword(''); setPage(1); }}
          />
        </div>

        {/* 工具列表 */}
        <Table
          columns={columns}
          dataSource={tools}
          rowKey="toolId"
          loading={loading}
          pagination={{
            current: page,
            pageSize: size,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 个工具`,
            onChange: (p, s) => { setPage(p); setSize(s); },
          }}
          size="middle"
        />

        {/* 注册/编辑 Modal */}
        <ToolFormModal
          open={registerOpen || !!editTool}
          editTool={editTool}
          onClose={() => { setRegisterOpen(false); setEditTool(null); }}
          onSuccess={loadTools}
        />

        {/* 详情 Drawer */}
        <DetailDrawer
          open={!!detailToolId}
          toolId={detailToolId}
          onClose={() => setDetailToolId(null)}
          onEdit={handleEditFromDetail}
        />
      </div>
    </div>
  );
}
