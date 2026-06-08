import axios from 'axios';
import { useStore } from '@/store';

const API_BASE = import.meta.env.VITE_SF_API_BASE_URL || '/agent/v1';
const AUTH_BASE = import.meta.env.VITE_SF_AUTH_BASE_URL || '/auth';
const SYSTEM_BASE = import.meta.env.VITE_SF_SYSTEM_BASE_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('shardflow_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default api;

export const systemApi = axios.create({
  baseURL: SYSTEM_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

systemApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('shardflow_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const authApi = axios.create({
  baseURL: AUTH_BASE,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// ---- Auth API ----

export interface AuthResult {
  token: string;
  refresh_token?: string;
  expires_in?: number;
  user_id: string;
  username?: string;
  role?: string;
}

export async function login(username: string, password: string): Promise<AuthResult> {
  const { data } = await authApi.post('/login', { username, password });
  const inner = data.data || data;
  return inner;
}

export async function register(username: string, password: string): Promise<AuthResult> {
  const { data } = await authApi.post('/register', { username, password });
  const inner = data.data || data;
  return inner;
}

export async function refreshToken(refreshTokenValue: string): Promise<{ token: string; refresh_token: string; expires_in?: number }> {
  const { data } = await authApi.post('/refresh', { refresh_token: refreshTokenValue });
  const inner = data.data || data;
  return inner;
}

// ---- 401 interceptor for auto token refresh ----

let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

function onTokenRefreshed(token: string) {
  refreshSubscribers.forEach(cb => cb(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

function handleAuthExpired() {
  localStorage.removeItem('shardflow_token');
  localStorage.removeItem('shardflow_refresh_token');
  localStorage.removeItem('shardflow_user_id');
  localStorage.removeItem('shardflow_token_expires_at');
  window.dispatchEvent(new CustomEvent('shardflow:auth-expired'));
}

async function doRefresh(): Promise<string | null> {
  const storedRefresh = localStorage.getItem('shardflow_refresh_token');
  if (!storedRefresh) return null;
  try {
    const result = await refreshToken(storedRefresh);
    localStorage.setItem('shardflow_token', result.token);
    if (result.refresh_token) {
      localStorage.setItem('shardflow_refresh_token', result.refresh_token);
    }
    if (result.expires_in) {
      localStorage.setItem('shardflow_token_expires_at', String(Date.now() + result.expires_in * 1000));
    }
    return result.token;
  } catch {
    return null;
  }
}

function attachAuthInterceptor(instance: ReturnType<typeof axios.create>) {
  instance.interceptors.response.use(
    res => res,
    async (error) => {
      const originalRequest = error.config;
      if (error.response?.status === 401 && !originalRequest._retry) {
        if (isRefreshing) {
          return new Promise(resolve => {
            addRefreshSubscriber((token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(instance(originalRequest));
            });
          });
        }
        originalRequest._retry = true;
        isRefreshing = true;
        try {
          const newToken = await doRefresh();
          if (newToken) {
            onTokenRefreshed(newToken);
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return instance(originalRequest);
          }
        } catch {
          // refresh failed
        } finally {
          isRefreshing = false;
        }
        handleAuthExpired();
      }
      return Promise.reject(error);
    }
  );
}

attachAuthInterceptor(api);
attachAuthInterceptor(systemApi);

// ---- Proactive token refresh ----
// 在 token 过期前主动刷新，避免请求失败

const REFRESH_AHEAD_SECONDS = 300; // 提前 5 分钟刷新

export function scheduleProactiveRefresh() {
  const expiresAt = localStorage.getItem('shardflow_token_expires_at');
  if (!expiresAt) return;

  const remaining = Number(expiresAt) - Date.now();
  if (remaining <= 0) {
    // 已过期，立即刷新
    doRefresh().catch(() => { /* 静默失败，等 401 拦截器处理 */ });
    return;
  }

  const refreshIn = Math.max(remaining - REFRESH_AHEAD_SECONDS * 1000, 0);
  setTimeout(() => {
    const currentToken = localStorage.getItem('shardflow_token');
    if (currentToken) {
      doRefresh().catch(() => { /* 静默失败 */ });
    }
  }, refreshIn);
}

// ---- SSE 401 处理辅助 ----

export async function getValidToken(): Promise<string | null> {
  const token = localStorage.getItem('shardflow_token');
  if (!token) return null;

  const expiresAt = localStorage.getItem('shardflow_token_expires_at');
  if (expiresAt && Date.now() > Number(expiresAt) - REFRESH_AHEAD_SECONDS * 1000) {
    const newToken = await doRefresh();
    return newToken;
  }
  return token;
}

// ---- Conversation API (SSE) ----

export async function sendConversation(
  taskId: string,
  message: string,
  sessionId: string,
  model: string,
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
  onError: (err: Error) => void,
  onDone: () => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = await getValidToken();
  const userId = localStorage.getItem('shardflow_user_id') || 'default';

  if (!token) {
    handleAuthExpired();
    onError(new Error('Authentication required'));
    return;
  }

  const response = await fetch(`${API_BASE}/conversation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      task_id: taskId,
      message,
      session_id: sessionId,
      user_id: userId,
      model,
      stream: true,
      kb_collection_name: useStore.getState().kbActiveMount.mounted
        ? `kb_chunks_${useStore.getState().userId}`
        : '',
    }),
    signal,
  });

  if (response.status === 401) {
    // 尝试刷新 token 后重试
    const newToken = await doRefresh();
    if (newToken) {
      return sendConversation(taskId, message, sessionId, model, onEvent, onError, onDone, signal);
    }
    handleAuthExpired();
    onError(new Error('Authentication expired'));
    return;
  }

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${response.statusText}${errorBody ? ` - ${errorBody}` : ''}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEventType = '';
  let lastEventTime = Date.now();

  // Stream timeout: if no data arrives for 60s, treat as disconnected
  const STREAM_TIMEOUT_MS = 60_000;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) { onDone(); break; }

      lastEventTime = Date.now();
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by blank lines (\n\n).
      // Split on \n to process line-by-line, keeping the last incomplete
      // line in the buffer for the next read cycle.
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        // Skip empty lines (event separators) and comments
        if (!line.trim() || line.startsWith(':')) {
          // When we hit a blank line after data, reset event type
          if (!line.trim()) currentEventType = '';
          continue;
        }
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim();
          continue;
        }
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent({ type: currentEventType || parsed.type || 'message', data: parsed.data || parsed });
            currentEventType = '';
          } catch {
            // Malformed JSON — skip but don't crash the stream
            console.warn('[SSE] Failed to parse data line:', line.slice(6).slice(0, 100));
          }
        }
      }

      // Check for stream timeout
      if (Date.now() - lastEventTime > STREAM_TIMEOUT_MS) {
        throw new Error('Stream timeout: no data received for 60 seconds');
      }
    }

    // Process any remaining data in the buffer after stream ends
    if (buffer.trim()) {
      const remainingLines = buffer.split('\n');
      for (const line of remainingLines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent({ type: currentEventType || parsed.type || 'message', data: parsed.data || parsed });
          } catch { /* skip */ }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      onDone();
    } else if (err instanceof TypeError && err.message.includes('network')) {
      onError(new Error('网络连接中断，请检查网络后重试'));
    } else if (err instanceof Error && err.message.startsWith('Stream timeout')) {
      onError(new Error('连接超时，服务器长时间未响应，请重试'));
    } else {
      onError(err instanceof Error ? err : new Error(String(err)));
    }
  }
}

// ---- Session API ----

export async function fetchTasks(): Promise<unknown[]> {
  const { data } = await api.get('/sessions');
  return data.sessions || data;
}

export async function createTask(title: string): Promise<{ task_id: string }> {
  const { data } = await api.post('/sessions', { title });
  return data;
}

// ---- Shard API ----

export async function fetchShard(taskId: string): Promise<unknown> {
  const { data } = await systemApi.get(`/shards/${taskId}`);
  return data.data || data;
}

// ---- Profile API ----

export async function fetchProfile(userId: string): Promise<unknown> {
  const { data } = await systemApi.get(`/profile/${userId}`);
  return data.data || data;
}

export async function updateProfile(userId: string, updates: Record<string, unknown>): Promise<unknown> {
  const { data } = await systemApi.put(`/profile/${userId}`, updates);
  return data.data || data;
}

// ---- Task History API ----

export async function fetchTaskHistory(params?: { status?: string; limit?: number; offset?: number }): Promise<unknown> {
  const { data } = await systemApi.get('/tasks', { params });
  return data.data || data;
}

// ---- MCP Tools API ----

export async function fetchMcpTools(status?: string): Promise<unknown> {
  const { data } = await systemApi.get('/mcp/registry/tools', { params: status ? { status } : {} });
  return data.data || data;
}

// ---- Strategy API ----

export async function searchStrategies(taskType: string, query: string, limit?: number): Promise<unknown> {
  const { data } = await systemApi.post('/strategies/search', { task_type: taskType, query, limit: limit || 5 });
  return data.data || data;
}

export async function submitStrategyFeedback(strategyId: string, feedback: string, comment?: string): Promise<unknown> {
  const { data } = await systemApi.post(`/strategies/${strategyId}/feedback`, { feedback, comment });
  return data.data || data;
}

// ---- Knowledge Base API ----

import type { KbCollection, KbDocument } from '@/types';

export async function fetchKbCollections(): Promise<KbCollection[]> {
  const { data } = await systemApi.get('/kb/collections');
  const result = data.data || data;
  return Array.isArray(result) ? result : Array.isArray(result?.collections) ? result.collections : [];
}

export async function createKbCollection(payload: { name: string; description?: string }): Promise<KbCollection> {
  const { data } = await systemApi.post('/kb/collections', payload);
  return data.data || data;
}

export async function updateKbCollection(id: string, payload: { name?: string; description?: string }): Promise<KbCollection> {
  const { data } = await systemApi.put(`/kb/collections/${id}`, payload);
  return data.data || data;
}

export async function deleteKbCollection(id: string): Promise<void> {
  await systemApi.delete(`/kb/collections/${id}`);
}

export async function fetchKbDocuments(collectionId: string): Promise<KbDocument[]> {
  const { data } = await systemApi.get(`/kb/collections/${collectionId}/documents`);
  const result = data.data || data;
  return Array.isArray(result) ? result : Array.isArray(result?.documents) ? result.documents : [];
}

export async function uploadKbDocument(
  collectionId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<KbDocument> {
  const token = await getValidToken();
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await axios.create({
    baseURL: SYSTEM_BASE,
    headers: { Authorization: `Bearer ${token}` },
  }).post(`/kb/collections/${collectionId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    },
  });
  return data.data || data;
}

export async function deleteKbDocument(documentId: string): Promise<void> {
  await systemApi.delete(`/kb/documents/${documentId}`);
}

// ---- Available Models API ----

export async function fetchAvailableModels(): Promise<Array<{ key: string; label: string; provider: string; model?: string; capabilities?: string; context_window?: number; type: string; is_verified?: boolean }>> {
  const { data } = await systemApi.get('/models/available');
  const inner = data.data || data;
  return inner.models || [];
}

// ---- Model Config API ----

export async function fetchModelConfig(modelId: string): Promise<Record<string, unknown>> {
  const { data } = await systemApi.get(`/models/${modelId}/config`);
  return data.data || data;
}

// ---- Custom Models API ----

/** Check if a Result-wrapped response body indicates an error (HTTP 200 but code != 200) */
function checkResultCode<T>(result: T): T {
  if (result && typeof result === 'object' && 'code' in result) {
    const code = (result as Record<string, unknown>).code as number;
    if (code !== 200) {
      const msg = ((result as Record<string, unknown>).message as string) || '操作失败';
      const err = new Error(msg) as Error & { code?: number };
      err.code = code;
      throw err;
    }
  }
  return result;
}

export async function fetchCustomModels(): Promise<unknown[]> {
  const { data } = await systemApi.get('/models/custom');
  const inner = data.data || data;
  return checkResultCode(inner).models || [];
}

export async function addCustomModelApi(payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await systemApi.post('/models/custom', payload);
  const inner = data.data || data;
  return checkResultCode(inner);
}

export async function updateCustomModelApi(id: string, payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await systemApi.put(`/models/custom/${id}`, payload);
  const inner = data.data || data;
  return checkResultCode(inner);
}

export async function deleteCustomModelApi(id: string): Promise<void> {
  const { data } = await systemApi.delete(`/models/custom/${id}`);
  checkResultCode(data.data || data);
}

// ---- Verify Custom Model ----

export async function verifyCustomModel(modelId: string): Promise<Record<string, unknown>> {
  const { data } = await systemApi.post('/models/custom/verify', { model_id: modelId });
  const result = data.data || data;
  // Defensive: if SaServletFilter returns HTTP 200 but body contains error code, treat as error
  if (result && typeof result === 'object' && 'code' in result && (result as Record<string, unknown>).code === 401) {
    const err = new Error('Unauthorized') as Error & { response?: { status?: number; data?: unknown } };
    err.response = { status: 401, data: result };
    throw err;
  }
  return result;
}

// ---- Agent Configs API ----

export async function fetchAgentConfigs(): Promise<unknown[]> {
  const { data } = await systemApi.get('/agents');
  const inner = data.data || data;
  return inner.agents || [];
}

export async function addAgentConfigApi(payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await systemApi.post('/agents', payload);
  return data.data || data;
}

export async function updateAgentConfigApi(id: string, payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await systemApi.put(`/agents/${id}`, payload);
  return data.data || data;
}

export async function deleteAgentConfigApi(id: string): Promise<void> {
  await systemApi.delete(`/agents/${id}`);
}
