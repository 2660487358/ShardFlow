import { useEffect, useRef, useState } from 'react';
import { Button, Alert, Space, message } from 'antd';
import { FormatPainterOutlined, WarningOutlined } from '@ant-design/icons';
import Editor, { Monaco } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';

interface ProtocolEditorProps {
  value: string;
  onChange: (value: string) => void;
  height?: string | number;
}

// Sensitive field patterns - same as in McpQuickSetupPage
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

export default function ProtocolEditor({ value, onChange, height = 600 }: ProtocolEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const [sensitiveWarnings, setSensitiveWarnings] = useState<string[]>([]);
  const [hasSyntaxErrors, setHasSyntaxErrors] = useState(false);

  function handleEditorDidMount(editor: editor.IStandaloneCodeEditor, monaco: Monaco) {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Configure JSON schema validation
    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
      validate: true,
      schemas: [{
        uri: 'http://shardflow/mcp-config-schema.json',
        fileMatch: ['*'],
        schema: {
          type: 'object',
          properties: {
            mcpServers: {
              type: 'object',
              description: 'MCP server configurations keyed by tool name',
              additionalProperties: {
                type: 'object',
                properties: {
                  transport: {
                    type: 'string',
                    enum: ['stdio', 'http-sse', 'cloud'],
                    description: 'Transport protocol type'
                  },
                  env: {
                    type: 'object',
                    description: 'Environment variables (sensitive fields should go here)',
                    additionalProperties: { type: 'string' }
                  },
                  connection: {
                    type: 'object',
                    description: 'Connection configuration',
                    properties: {
                      url: { type: 'string', description: 'Server URL for http-sse transport' },
                      command: { type: 'string', description: 'Command to execute for stdio transport' },
                      args: { type: 'array', items: { type: 'string' }, description: 'Command arguments' },
                      provider: { type: 'string', enum: ['smithery', 'google-managed'] },
                      server_key: { type: 'string', description: 'Smithery server key' },
                      server_id: { type: 'string', description: 'Google Managed server ID' }
                    }
                  },
                  timeoutSeconds: { type: 'number', minimum: 1, maximum: 300, default: 30 },
                  retryCount: { type: 'number', minimum: 0, maximum: 5, default: 2 }
                },
                required: ['transport']
              }
            }
          },
          required: ['mcpServers']
        }
      }],
      enableSchemaRequest: false,
      allowComments: false,
      trailingCommas: 'error'
    });

    // Listen for content changes
    editor.onDidChangeModelContent(() => {
      const currentValue = editor.getValue();
      onChange(currentValue);
      validateSensitiveFields(currentValue);
      checkSyntaxErrors();
    });

    // Initial validation
    validateSensitiveFields(value);
    checkSyntaxErrors();
  }

  function validateSensitiveFields(jsonString: string) {
    try {
      const config = JSON.parse(jsonString);
      const warnings: string[] = [];

      if (config.mcpServers) {
        Object.entries(config.mcpServers).forEach(([serverName, serverConfig]: [string, any]) => {
          // Check connection.args for sensitive fields
          if (serverConfig?.connection?.args) {
            const args = serverConfig.connection.args;
            if (Array.isArray(args)) {
              args.forEach((arg: string) => {
                // Check if arg contains key=value pattern with sensitive field
                const match = arg.match(/^([^=]+)=(.+)$/);
                if (match) {
                  const [, key] = match;
                  if (isSensitiveField(key)) {
                    warnings.push(`服务器 "${serverName}" 的 connection.args 中包含敏感字段 "${key}"，建议移至 env`);
                  }
                }
              });
            }
          }

          // Check connection object for sensitive fields
          if (serverConfig?.connection) {
            const connection = serverConfig.connection;
            ['url', 'command', 'server_key', 'server_id'].forEach(field => {
              if (connection[field] && typeof connection[field] === 'string') {
                // Check if the value looks like it contains a sensitive token
                if (connection[field].length > 50 || /[a-zA-Z0-9]{20,}/.test(connection[field])) {
                  if (field !== 'url' && field !== 'command') {
                    warnings.push(`服务器 "${serverName}" 的 connection.${field} 可能包含敏感值，建议移至 env`);
                  }
                }
              }
            });
          }
        });
      }

      setSensitiveWarnings(warnings);
    } catch {
      // JSON parse error - ignore
    }
  }

  function checkSyntaxErrors() {
    if (!editorRef.current || !monacoRef.current) return;

    const model = editorRef.current.getModel();
    if (!model) return;

    const markers = monacoRef.current.editor.getModelMarkers({ resource: model.uri });
    const hasErrors = markers.some((marker: editor.IMarker) => marker.severity === monacoRef.current!.MarkerSeverity.Error);
    setHasSyntaxErrors(hasErrors);
  }

  function handleNormalize() {
    try {
      const config = JSON.parse(value);
      let modified = false;

      if (config.mcpServers) {
        Object.keys(config.mcpServers).forEach(serverName => {
          const serverConfig = config.mcpServers[serverName];

          // Ensure env exists
          if (!serverConfig.env) {
            serverConfig.env = {};
          }

          // Move sensitive fields from args to env
          if (serverConfig.connection?.args) {
            const newArgs: string[] = [];
            serverConfig.connection.args.forEach((arg: string) => {
              const match = arg.match(/^([^=]+)=(.+)$/);
              if (match) {
                const [, key, val] = match;
                if (isSensitiveField(key)) {
                  serverConfig.env[key] = val;
                  modified = true;
                } else {
                  newArgs.push(arg);
                }
              } else {
                newArgs.push(arg);
              }
            });
            if (modified) {
              serverConfig.connection.args = newArgs;
            }
          }
        });
      }

      if (modified) {
        const normalized = JSON.stringify(config, null, 2);
        onChange(normalized);
        message.success('已将敏感字段移至 env');
      } else {
        message.info('未发现需要规范化的敏感字段');
      }
    } catch (err) {
      message.error('JSON 格式错误，无法规范化');
    }
  }

  function handleEditorChange(newValue: string | undefined) {
    if (newValue !== undefined) {
      onChange(newValue);
      validateSensitiveFields(newValue);
      checkSyntaxErrors();
    }
  }

  return (
    <div>
      <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
        {hasSyntaxErrors && (
          <Alert
            message="JSON 语法错误"
            description="配置文件存在语法错误，请检查红色波浪线标记的位置"
            type="error"
            showIcon
            icon={<WarningOutlined />}
          />
        )}

        {sensitiveWarnings.length > 0 && (
          <Alert
            message="安全警告"
            description={
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {sensitiveWarnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            }
            type="warning"
            showIcon
            action={
              <Button size="small" type="primary" onClick={handleNormalize}>
                一键规范化
              </Button>
            }
          />
        )}

        <div style={{ marginBottom: 8 }}>
          <Button
            icon={<FormatPainterOutlined />}
            onClick={handleNormalize}
            disabled={hasSyntaxErrors}
          >
            一键规范化
          </Button>
        </div>
      </Space>

      <Editor
        height={height}
        defaultLanguage="json"
        value={value}
        onChange={handleEditorChange}
        onMount={handleEditorDidMount}
        theme="vs-light"
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: 'on',
          folding: true,
          renderWhitespace: 'selection',
          quickSuggestions: true,
          suggestOnTriggerCharacters: true,
          acceptSuggestionOnEnter: 'on',
          formatOnPaste: true,
          formatOnType: true,
        }}
      />
    </div>
  );
}
