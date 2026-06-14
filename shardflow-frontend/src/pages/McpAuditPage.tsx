import { useState, useEffect, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Typography, Table, Tabs, Select, Input, Tag, message, Space,
} from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { McpMetadataAuditEntry, McpCallAuditEntry } from '@/types';
import { fetchMcpMetadataAuditLogs, fetchMcpCallAuditLogs } from '@/api/client';

const { Title, Text } = Typography;

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

const OPERATION_TYPE_OPTIONS = [
  { value: '', label: '全部操作' },
  { value: 'REGISTER', label: '注册' },
  { value: 'UPDATE', label: '更新' },
  { value: 'STATUS_CHANGE', label: '状态变更' },
  { value: 'DELETE', label: '删除' },
  { value: 'ROLLBACK', label: '回滚' },
];

const CALL_STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'SUCCESS', label: '成功' },
  { value: 'FAILED', label: '失败' },
  { value: 'TIMEOUT', label: '超时' },
];

function operationTypeTag(type: string) {
  const map: Record<string, { color: string; label: string }> = {
    REGISTER: { color: 'success', label: '注册' },
    UPDATE: { color: 'processing', label: '更新' },
    STATUS_CHANGE: { color: 'warning', label: '状态变更' },
    DELETE: { color: 'error', label: '删除' },
    ROLLBACK: { color: 'purple', label: '回滚' },
  };
  const info = map[type] || { color: 'default', label: type };
  return <Tag color={info.color}>{info.label}</Tag>;
}

function callStatusTag(status: string) {
  const map: Record<string, { color: string; label: string }> = {
    SUCCESS: { color: 'success', label: '成功' },
    FAILED: { color: 'error', label: '失败' },
    TIMEOUT: { color: 'warning', label: '超时' },
  };
  const info = map[status] || { color: 'default', label: status };
  return <Tag color={info.color}>{info.label}</Tag>;
}

// ── Metadata Audit Tab ──

function MetadataAuditTab() {
  const [logs, setLogs] = useState<McpMetadataAuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [operationType, setOperationType] = useState('');
  const [toolId, setToolId] = useState('');

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchMcpMetadataAuditLogs({
        operationType: operationType || undefined,
        toolId: toolId || undefined,
        page,
        size,
      });
      setLogs((result.logs || []) as McpMetadataAuditEntry[]);
      setTotal(result.total || 0);
    } catch {
      message.error('获取操作审计日志失败');
    } finally {
      setLoading(false);
    }
  }, [operationType, toolId, page, size]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const columns: ColumnsType<McpMetadataAuditEntry> = [
    {
      title: '操作人',
      dataIndex: 'operator',
      width: 120,
    },
    {
      title: '操作类型',
      dataIndex: 'operationType',
      width: 120,
      render: (t: string) => operationTypeTag(t),
    },
    {
      title: '工具名称',
      dataIndex: 'toolName',
      width: 160,
    },
    {
      title: '变更摘要',
      dataIndex: 'changeSummary',
      ellipsis: true,
    },
    {
      title: '操作时间',
      dataIndex: 'operationAt',
      width: 180,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          value={operationType}
          onChange={(v) => { setOperationType(v); setPage(1); }}
          options={OPERATION_TYPE_OPTIONS}
          style={{ width: 140 }}
        />
        <Input
          placeholder="按 Tool ID 筛选..."
          value={toolId}
          onChange={(e) => setToolId(e.target.value)}
          onPressEnter={() => { setPage(1); loadLogs(); }}
          style={{ width: 220 }}
          allowClear
          onClear={() => { setToolId(''); setPage(1); }}
          prefix={<SearchOutlined />}
        />
      </div>
      <Table
        columns={columns}
        dataSource={logs}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: size,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条记录`,
          onChange: (p, s) => { setPage(p); setSize(s); },
        }}
        size="middle"
      />
    </div>
  );
}

// ── Call Audit Tab ──

function CallAuditTab() {
  const [logs, setLogs] = useState<McpCallAuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState('');
  const [toolId, setToolId] = useState('');

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchMcpCallAuditLogs({
        status: statusFilter || undefined,
        toolId: toolId || undefined,
        page,
        size,
      });
      setLogs((result.logs || []) as McpCallAuditEntry[]);
      setTotal(result.total || 0);
    } catch {
      message.error('获取调用审计日志失败');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toolId, page, size]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const columns: ColumnsType<McpCallAuditEntry> = [
    {
      title: '工具名称',
      dataIndex: 'toolName',
      width: 140,
    },
    {
      title: '版本',
      dataIndex: 'toolVersion',
      width: 80,
      render: (v: string) => <Tag>v{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => callStatusTag(s),
    },
    {
      title: '延迟',
      dataIndex: 'latencyMs',
      width: 100,
      render: (ms: number) => (
        <Text style={{ color: ms > 3000 ? '#cf1322' : ms > 1000 ? '#fa8c16' : undefined }}>
          {ms}ms
        </Text>
      ),
    },
    {
      title: '错误信息',
      dataIndex: 'errorMsg',
      width: 200,
      ellipsis: true,
      render: (msg: string) => msg || '-',
    },
    {
      title: 'Trace ID',
      dataIndex: 'traceId',
      width: 140,
      ellipsis: true,
    },
    {
      title: '请求时间',
      dataIndex: 'requestAt',
      width: 180,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          value={statusFilter}
          onChange={(v) => { setStatusFilter(v); setPage(1); }}
          options={CALL_STATUS_OPTIONS}
          style={{ width: 140 }}
        />
        <Input
          placeholder="按 Tool ID 筛选..."
          value={toolId}
          onChange={(e) => setToolId(e.target.value)}
          onPressEnter={() => { setPage(1); loadLogs(); }}
          style={{ width: 220 }}
          allowClear
          onClear={() => { setToolId(''); setPage(1); }}
          prefix={<SearchOutlined />}
        />
      </div>
      <Table
        columns={columns}
        dataSource={logs}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize: size,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条记录`,
          onChange: (p, s) => { setPage(p); setSize(s); },
        }}
        size="middle"
      />
    </div>
  );
}

// ── Main Page ──

export default function McpAuditPage() {
  const { isAuthenticated } = useOutletContext<OutletContext>();

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Text type="secondary" style={{ fontSize: 16 }}>请先登录以查看审计日志</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '32px 40px', height: '100%', overflow: 'auto' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <Title level={3} style={{ margin: 0, color: 'var(--ink)', letterSpacing: '0.05em' }}>审计日志</Title>
          <Text type="secondary" style={{ fontSize: 13 }}>查看 MCP 工具的操作审计和调用审计记录</Text>
        </div>

        <Tabs items={[
          {
            key: 'metadata',
            label: '操作审计',
            children: <MetadataAuditTab />,
          },
          {
            key: 'calls',
            label: '调用审计',
            children: <CallAuditTab />,
          },
        ]} />
      </div>
    </div>
  );
}
