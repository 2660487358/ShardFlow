import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Typography, Steps, Button, Card, Form, Input, Select, InputNumber,
  Collapse, Space, Alert, Spin, message, Drawer, Tag, Row, Col, Tabs, Switch
} from 'antd';
import {
  CheckOutlined, EyeOutlined, SaveOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import type { McpTemplate, QuickConfigRequest, QuickConfigResponse } from '@/types';
import { fetchMcpTemplateDetail, quickSetupMcp, testMcpConnection } from '@/api/client';
import TemplateSelector from '@/components/mcp/TemplateSelector';
import ProtocolEditor from '@/components/mcp/ProtocolEditor';

const { Title, Text, Paragraph } = Typography;
const { Panel } = Collapse;
const { TextArea } = Input;

const SENSITIVE_FIELD_PATTERNS = [
  /token/i,
  /secret/i,
  /password/i,
  /api_key/i,
  /key$/i,
  /apikey/i,
  /access_key/i,
  /private_key/i,
];

function isSensitiveField(fieldName: string): boolean {
  return SENSITIVE_FIELD_PATTERNS.some(pattern => pattern.test(fieldName));
}

export default function McpQuickSetupPage() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedTemplate, setSelectedTemplate] = useState<McpTemplate | null>(null);
  const [templateDetail, setTemplateDetail] = useState<any>(null);
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [envFields, setEnvFields] = useState<Record<string, string>>({});
  const [showPassword, setShowPassword] = useState<Record<string, boolean>>({});
  const [previewVisible, setPreviewVisible] = useState(false);
  const [customParams, setCustomParams] = useState<Array<{ key: string; value: string }>>([]);
  const [mode, setMode] = useState<'form' | 'protocol'>('form');
  const [protocolValue, setProtocolValue] = useState<string>('');
  const [autoStart, setAutoStart] = useState<boolean>(false); // P6: SSE autoStart 开关状态

  // Convert QuickConfigRequest to protocol JSON format
  function requestToProtocol(request: QuickConfigRequest): string {
    const protocol: any = {
      mcpServers: {
        [request.name]: {
          transport: request.transport,
          connection: request.connection || {},
          timeoutSeconds: request.timeoutSeconds || 30,
          retryCount: request.retryCount || 2,
        }
      }
    };

    if (request.env && Object.keys(request.env).length > 0) {
      protocol.mcpServers[request.name].env = request.env;
    }

    return JSON.stringify(protocol, null, 2);
  }

  // Convert protocol JSON to QuickConfigRequest
  function protocolToRequest(protocolJson: string): QuickConfigRequest | null {
    try {
      const protocol = JSON.parse(protocolJson);
      const serverNames = Object.keys(protocol.mcpServers || {});

      if (serverNames.length === 0) {
        message.error('协议 JSON 中未找到 mcpServers 配置');
        return null;
      }

      const serverName = serverNames[0];
      const serverConfig = protocol.mcpServers[serverName];

      const request: QuickConfigRequest = {
        name: serverName,
        displayName: serverName,
        template: selectedTemplate?.templateId || '',
        transport: serverConfig.transport,
        connection: serverConfig.connection || {},
        env: serverConfig.env,
        timeoutSeconds: serverConfig.timeoutSeconds,
        retryCount: serverConfig.retryCount,
      };

      return request;
    } catch (err) {
      message.error('协议 JSON 格式错误');
      return null;
    }
  }

  // Sync form and protocol values when mode changes
  useEffect(() => {
    if (mode === 'protocol' && selectedTemplate) {
      // Convert current form data to protocol JSON
      const request = buildRequest();
      const protocol = requestToProtocol(request);
      setProtocolValue(protocol);
    }
  }, [mode]);

  // Handle protocol editor changes
  function handleProtocolChange(newValue: string) {
    setProtocolValue(newValue);
  }

  useEffect(() => {
    if (selectedTemplate) {
      loadTemplateDetail();
    }
  }, [selectedTemplate]);

  async function loadTemplateDetail() {
    if (!selectedTemplate) return;
    setLoading(true);
    try {
      const detail = await fetchMcpTemplateDetail(selectedTemplate.templateId);
      setTemplateDetail(detail);

      // Initialize env fields from template
      const initialEnv: Record<string, string> = {};
      if (detail.envVarDescriptions) {
        Object.keys(detail.envVarDescriptions).forEach(key => {
          initialEnv[key] = '';
        });
      }
      setEnvFields(initialEnv);

      // Auto-generate tool name
      form.setFieldsValue({
        name: selectedTemplate.templateId.replace(/-/g, '_'),
        displayName: selectedTemplate.displayName,
      });
    } catch (error) {
      message.error('加载模板详情失败');
    } finally {
      setLoading(false);
    }
  }

  function handleTemplateSelect(template: McpTemplate) {
    setSelectedTemplate(template);
    setCurrentStep(1);
  }

  function handleEnvFieldChange(key: string, value: string) {
    setEnvFields(prev => ({ ...prev, [key]: value }));
  }

  function togglePasswordVisibility(key: string) {
    setShowPassword(prev => ({ ...prev, [key]: !prev[key] }));
  }

  function addCustomParam() {
    setCustomParams(prev => [...prev, { key: '', value: '' }]);
  }

  function removeCustomParam(index: number) {
    setCustomParams(prev => prev.filter((_, i) => i !== index));
  }

  function updateCustomParam(index: number, key: string, value: string) {
    setCustomParams(prev => {
      const updated = [...prev];
      updated[index] = { key, value };
      return updated;
    });
  }

  function buildRequest(): QuickConfigRequest {
    const values = form.getFieldsValue();

    // If in protocol mode, parse from protocol JSON
    if (mode === 'protocol') {
      const request = protocolToRequest(protocolValue);
      if (request) {
        return request;
      }
      // Fall back to form values if protocol parsing fails
    }

    // Build env object - sensitive fields go to env
    const env: Record<string, string> = { ...envFields };

    // Add custom params - check for duplicates
    customParams.forEach(param => {
      if (param.key) {
        if (isSensitiveField(param.key)) {
          env[param.key] = param.value;
        }
      }
    });

    // P6: Build connection with autoStart
    const connection = { ...templateDetail?.defaultConnection } || {};
    if (selectedTemplate?.transport === 'http-sse' && autoStart) {
      connection.autoStart = true;
    }

    const request: QuickConfigRequest = {
      name: values.name,
      displayName: values.displayName,
      template: selectedTemplate!.templateId,
      transport: selectedTemplate!.transport,
      connection: connection,
      env: Object.keys(env).length > 0 ? env : undefined,
      timeoutSeconds: values.timeoutSeconds,
      retryCount: values.retryCount,
    };

    return request;
  }

  async function handleSave() {
    try {
      await form.validateFields();
      setLoading(true);

      const request = buildRequest();
      const result = await quickSetupMcp(request);

      message.success('配置保存成功');
      message.info(`工具 ID: ${result.toolId}`);
      navigate('/mcp-tools');
    } catch (error: any) {
      message.error(error.message || '保存失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleTest() {
    try {
      await form.validateFields();
      setTesting(true);

      const request = buildRequest();
      const result = await testMcpConnection(request.name, request);

      if (result.success) {
        message.success(`连接测试成功 (${result.latencyMs}ms)`);
      } else {
        message.error(`连接测试失败: ${result.message}`);
      }
    } catch (error: any) {
      message.error(error.message || '测试失败');
    } finally {
      setTesting(false);
    }
  }

  const steps = [
    {
      title: '选择模板',
      content: (
        <TemplateSelector
          onSelect={handleTemplateSelect}
          selectedTemplateId={selectedTemplate?.templateId}
        />
      ),
    },
    {
      title: '配置参数',
      content: loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
        </div>
      ) : (
        <Card>
          <Tabs
            activeKey={mode}
            onChange={(key) => setMode(key as 'form' | 'protocol')}
            items={[
              {
                key: 'form',
                label: '表单模式',
                children: (
                  <Form form={form} layout="vertical">
                    <Form.Item
                      name="name"
                      label="工具名称"
                      rules={[
                        { required: true, message: '请输入工具名称' },
                        { pattern: /^[a-zA-Z0-9_]+$/, message: '只能包含字母、数字和下划线' },
                      ]}
                    >
                      <Input placeholder="例如: feishu_calendar" />
                    </Form.Item>

                    <Form.Item name="displayName" label="显示名称">
                      <Input placeholder="工具的友好名称" />
                    </Form.Item>

                    <Alert
                      message="传输协议"
                      description={
                        <Space>
                          <Tag color="blue">{selectedTemplate?.transport}</Tag>
                          <Text type="secondary">由模板预设，不可修改</Text>
                        </Space>
                      }
                      type="info"
                      style={{ marginBottom: 24 }}
                    />

                    <Title level={5}>认证信息</Title>
                    {templateDetail?.envVarDescriptions && Object.keys(templateDetail.envVarDescriptions).length > 0 ? (
                      Object.entries(templateDetail.envVarDescriptions).map(([key, description]) => (
                        <Form.Item key={key} label={key} help={description as string}>
                          <Input
                            type={showPassword[key] ? 'text' : 'password'}
                            value={envFields[key] || ''}
                            onChange={(e) => handleEnvFieldChange(key, e.target.value)}
                            placeholder={`请输入 ${key}`}
                            suffix={
                              <Button
                                type="text"
                                icon={showPassword[key] ? <EyeOutlined /> : <EyeOutlined />}
                                onClick={() => togglePasswordVisibility(key)}
                              />
                            }
                          />
                        </Form.Item>
                      ))
                    ) : (
                      <Text type="secondary">此模板无需认证信息</Text>
                    )}

                    <Collapse style={{ marginTop: 24 }}>
                      <Panel header="高级选项" key="advanced">
                        {/* P6: SSE 模式显示 autoStart 开关 */}
                        {selectedTemplate?.transport === 'http-sse' && (
                          <Form.Item
                            label="自动启动本地服务"
                            help="启用后，系统将自动启动本地 MCP Server 子进程"
                          >
                            <Switch
                              checked={autoStart}
                              onChange={(checked) => setAutoStart(checked)}
                              checkedChildren="开启"
                              unCheckedChildren="关闭"
                            />
                          </Form.Item>
                        )}
                        <Form.Item name="timeoutSeconds" label="超时时间（秒）">
                          <InputNumber min={1} max={300} defaultValue={30} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item name="retryCount" label="重试次数">
                          <InputNumber min={0} max={5} defaultValue={2} style={{ width: '100%' }} />
                        </Form.Item>
                      </Panel>
                    </Collapse>

                    <Card
                      title="自定义参数"
                      style={{ marginTop: 24 }}
                      extra={<Button onClick={addCustomParam}>添加参数</Button>}
                    >
                      {customParams.length === 0 ? (
                        <Text type="secondary">暂无自定义参数</Text>
                      ) : (
                        customParams.map((param, index) => (
                          <Row key={index} gutter={16} style={{ marginBottom: 12 }}>
                            <Col span={10}>
                              <Input
                                placeholder="参数名"
                                value={param.key}
                                onChange={(e) => updateCustomParam(index, e.target.value, param.value)}
                              />
                            </Col>
                            <Col span={10}>
                              <Input
                                placeholder="参数值"
                                value={param.value}
                                onChange={(e) => updateCustomParam(index, param.key, e.target.value)}
                              />
                            </Col>
                            <Col span={4}>
                              <Button danger onClick={() => removeCustomParam(index)}>
                                删除
                              </Button>
                            </Col>
                          </Row>
                        ))
                      )}
                    </Card>

                    <Button
                      type="link"
                      onClick={() => setPreviewVisible(true)}
                      style={{ marginTop: 16 }}
                    >
                      查看 JSON 预览
                    </Button>
                  </Form>
                ),
              },
              {
                key: 'protocol',
                label: '协议模式',
                children: (
                  <div>
                    <Alert
                      message="协议模式"
                      description="直接编辑 MCP 配置 JSON，支持 IntelliSense 和实时校验"
                      type="info"
                      style={{ marginBottom: 16 }}
                    />
                    <ProtocolEditor
                      value={protocolValue}
                      onChange={handleProtocolChange}
                      height={500}
                    />
                  </div>
                ),
              },
            ]}
          />
        </Card>
      ),
    },
    {
      title: '保存并测试',
      content: (
        <Card>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Alert
              message="配置完成"
              description="检查以下信息是否正确，然后保存配置"
              type="success"
              showIcon
            />

            <div>
              <Text strong>工具名称：</Text>
              <Text>{form.getFieldValue('name')}</Text>
            </div>

            <div>
              <Text strong>模板：</Text>
              <Text>{selectedTemplate?.displayName}</Text>
            </div>

            <div>
              <Text strong>传输协议：</Text>
              <Tag color="blue">{selectedTemplate?.transport}</Tag>
            </div>

            <Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
              >
                保存配置
              </Button>
              <Button
                icon={<ThunderboltOutlined />}
                onClick={handleTest}
                loading={testing}
              >
                测试连接
              </Button>
            </Space>
          </Space>
        </Card>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>MCP 快速配置</Title>

      <Steps current={currentStep} style={{ marginBottom: 24 }}>
        {steps.map((item) => (
          <Steps.Step key={item.title} title={item.title} />
        ))}
      </Steps>

      <div>{steps[currentStep].content}</div>

      <div style={{ marginTop: 24 }}>
        {currentStep > 0 && (
          <Button style={{ marginRight: 8 }} onClick={() => setCurrentStep(currentStep - 1)}>
            上一步
          </Button>
        )}
        {currentStep < steps.length - 1 && selectedTemplate && (
          <Button type="primary" onClick={() => setCurrentStep(currentStep + 1)}>
            下一步
          </Button>
        )}
      </div>

      <Drawer
        title="JSON 预览"
        placement="right"
        width={600}
        open={previewVisible}
        onClose={() => setPreviewVisible(false)}
      >
        <TextArea
          value={JSON.stringify(buildRequest(), null, 2)}
          autoSize={{ minRows: 20, maxRows: 40 }}
          readOnly
        />
      </Drawer>
    </div>
  );
}
