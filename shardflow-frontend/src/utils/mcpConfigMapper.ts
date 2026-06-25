/**
 * MCP 配置双向映射工具 (P6)
 *
 * 职责：
 * 1. formToProtocol：表单数据 → 协议 JSON
 * 2. protocolToForm：协议 JSON → 表单数据
 * 3. detectConflicts：检测 args 与 env 之间的冲突
 *
 * 冲突检测规则：
 * - 同一参数在 args 和 env 重复出现 → 弹出选择对话框
 * - 自定义值覆盖模板默认值 → 弹出确认对话框
 * - 解决策略：自定义值优先于默认值，但需用户确认
 */

import type { QuickConfigRequest } from '@/types';

export interface Conflict {
  field: string;
  type: 'args_env_duplicate' | 'custom_override_default';
  argsValue?: string;
  envValue?: string;
  description: string;
}

export interface ConflictResolution {
  field: string;
  resolution: 'use_args' | 'use_env' | 'skip';
}

/**
 * 表单数据 → 协议 JSON 字符串
 *
 * 转换映射表：
 * | 表单字段           | 协议路径                      |
 * |-------------------|-------------------------------|
 * | name              | mcpServers.{name}             |
 * | template          | _template（标识字段）          |
 * | transport         | mcpServers.{name}.transport   |
 * | connection.command| mcpServers.{name}.connection.command |
 * | connection.args   | mcpServers.{name}.connection.args   |
 * | connection.url    | mcpServers.{name}.connection.url    |
 * | connection.provider| mcpServers.{name}.connection.provider |
 * | env               | mcpServers.{name}.env          |
 * | timeoutSeconds    | mcpServers.{name}.timeoutSeconds    |
 * | retryCount        | mcpServers.{name}.retryCount   |
 */
export function formToProtocol(config: QuickConfigRequest): string {
  const protocol: Record<string, unknown> = {
    mcpServers: {
      [config.name]: {
        transport: config.transport,
      },
    },
  };

  const serverConfig = (protocol.mcpServers as Record<string, unknown>)[config.name] as Record<string, unknown>;

  // 添加 _template 标识字段（用于 UI 识别，不参与运行）
  serverConfig._template = config.template;
  if (config.displayName) {
    serverConfig._displayName = config.displayName;
  }

  // connection 映射
  const connection: Record<string, unknown> = {};
  if (config.connection) {
    if (config.connection.url) connection.url = config.connection.url;
    if (config.connection.command) connection.command = config.connection.command;
    if (config.connection.args && config.connection.args.length > 0) connection.args = config.connection.args;
    if (config.connection.provider) connection.provider = config.connection.provider;
    if (config.connection.server_key) connection.server_key = config.connection.server_key;
    if (config.connection.server_id) connection.server_id = config.connection.server_id;
    if (config.connection.autoStart) connection.autoStart = config.connection.autoStart;
  }
  if (Object.keys(connection).length > 0) {
    serverConfig.connection = connection;
  }

  // env 映射
  if (config.env && Object.keys(config.env).length > 0) {
    serverConfig.env = { ...config.env };
  }

  // 高级选项
  if (config.timeoutSeconds !== undefined) {
    serverConfig.timeoutSeconds = config.timeoutSeconds;
  }
  if (config.retryCount !== undefined) {
    serverConfig.retryCount = config.retryCount;
  }

  return JSON.stringify(protocol, null, 2);
}

/**
 * 协议 JSON → 表单数据
 */
export function protocolToForm(protocolJson: string): QuickConfigRequest | null {
  try {
    const protocol = JSON.parse(protocolJson);
    const serverNames = Object.keys(protocol.mcpServers || {});

    if (serverNames.length === 0) {
      return null;
    }

    const serverName = serverNames[0];
    const serverConfig = protocol.mcpServers[serverName] || {};

    const request: QuickConfigRequest = {
      name: serverName,
      displayName: serverConfig._displayName || serverName,
      template: serverConfig._template || '',
      transport: serverConfig.transport || 'http-sse',
      connection: serverConfig.connection || {},
      env: serverConfig.env || undefined,
      timeoutSeconds: serverConfig.timeoutSeconds,
      retryCount: serverConfig.retryCount,
    };

    // 清理空的 env
    if (request.env && Object.keys(request.env).length === 0) {
      request.env = undefined;
    }

    return request;
  } catch {
    return null;
  }
}

/**
 * 检测冲突
 *
 * 检查规则：
 * 1. args_env_duplicate: 同一参数名称同时在 connection.args 和 env 中出现
 * 2. custom_override_default: 自定义参数覆盖了 env 中的默认值
 */
export function detectConflicts(
  formData: QuickConfigRequest | null,
  protocolData: QuickConfigRequest | null,
): Conflict[] {
  const conflicts: Conflict[] = [];

  if (!formData && !protocolData) return conflicts;

  // 如果某一边为 null，用另一边替代
  const form = formData || protocolData;
  const protocol = protocolData || formData;

  if (!form || !protocol) return conflicts;

  // 规则1: 同一参数在 args 和 env 重复出现
  const formArgs = extractArgsFromConnection(form.connection);
  const protoArgs = extractArgsFromConnection(protocol.connection);
  const allArgs = [...new Set([...formArgs, ...protoArgs])];
  const formEnv = form.env || {};
  const protoEnv = protocol.env || {};

  for (const arg of allArgs) {
    const inFormEnv = arg in formEnv;
    const inProtoEnv = arg in protoEnv;
    if (inFormEnv || inProtoEnv) {
      conflicts.push({
        field: arg,
        type: 'args_env_duplicate',
        argsValue: arg, // arg 名称本身
        envValue: formEnv[arg] || protoEnv[arg],
        description: `参数 "${arg}" 同时出现在 args 和 env 中，请选择使用位置`,
      });
    }
  }

  // 规则2: 自定义值覆盖模板默认值（form 和 protocol 中同名但值不同）
  const allEnvKeys = new Set([...Object.keys(formEnv), ...Object.keys(protoEnv)]);
  for (const key of allEnvKeys) {
    if (formEnv[key] && protoEnv[key] && formEnv[key] !== protoEnv[key]) {
      conflicts.push({
        field: key,
        type: 'custom_override_default',
        argsValue: formEnv[key],
        envValue: protoEnv[key],
        description: `自定义值 "${formEnv[key]}" 将覆盖默认值 "${protoEnv[key]}"`,
      });
    }
  }

  return conflicts;
}

/**
 * 应用冲突解决策略
 */
export function applyResolutions(
  request: QuickConfigRequest,
  resolutions: ConflictResolution[],
  conflicts: Conflict[],
): QuickConfigRequest {
  const result: QuickConfigRequest = {
    ...request,
    connection: { ...request.connection },
    env: request.env ? { ...request.env } : undefined,
  };

  for (const resolution of resolutions) {
    const conflict = conflicts.find(c => c.field === resolution.field);
    if (!conflict) continue;

    if (conflict.type === 'args_env_duplicate') {
      if (resolution.resolution === 'use_args') {
        // 从 env 中移除
        if (result.env) {
          delete result.env[resolution.field];
          if (Object.keys(result.env).length === 0) {
            (result as unknown as Record<string, unknown>).env = undefined;
          }
        }
      } else if (resolution.resolution === 'use_env') {
        // 从 connection.args 中移除
        const envValue = conflict.envValue || '';
        if (!result.env) {
          result.env = {};
        }
        result.env[resolution.field] = envValue;
        // 从 connection 中移除 args 中对应的项
        const conn = result.connection as Record<string, unknown>;
        if (conn.args && Array.isArray(conn.args)) {
          conn.args = conn.args.filter((a: string) => !a.includes(resolution.field));
        }
      }
    } else if (conflict.type === 'custom_override_default') {
      // 自定义值优先，已在 request 中
      // 只需记录日志，无需实际操作
    }
  }

  return result;
}

/**
 * 从 connection 对象中提取 args 参数名列表
 */
function extractArgsFromConnection(connection: Record<string, unknown> | undefined): string[] {
  if (!connection || !connection.args || !Array.isArray(connection.args)) return [];

  const argNames: string[] = [];
  for (let i = 0; i < connection.args.length; i++) {
    const arg = connection.args[i];
    if (typeof arg === 'string' && arg.startsWith('--')) {
      // --key=value 或 --key 格式
      const eqIndex = arg.indexOf('=');
      if (eqIndex > 0) {
        argNames.push(arg.slice(2, eqIndex));
      } else if (i + 1 < connection.args.length && !connection.args[i + 1].startsWith('-')) {
        argNames.push(arg.slice(2));
      }
    }
  }
  return argNames;
}
