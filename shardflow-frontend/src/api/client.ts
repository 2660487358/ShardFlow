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

export async function refreshToken(refreshTokenValue: string): Promise<{ token: string }> {
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
          const storedRefresh = localStorage.getItem('shardflow_refresh_token');
          if (storedRefresh) {
            const result = await refreshToken(storedRefresh);
            localStorage.setItem('shardflow_token', result.token);
            onTokenRefreshed(result.token);
            originalRequest.headers.Authorization = `Bearer ${result.token}`;
            return instance(originalRequest);
          }
        } catch {
          localStorage.removeItem('shardflow_token');
          localStorage.removeItem('shardflow_refresh_token');
          localStorage.removeItem('shardflow_user_id');
          window.dispatchEvent(new CustomEvent('shardflow:auth-expired'));
        } finally {
          isRefreshing = false;
        }
      }
      return Promise.reject(error);
    }
  );
}

attachAuthInterceptor(api);
attachAuthInterceptor(systemApi);

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
  const token = localStorage.getItem('shardflow_token');
  const userId = localStorage.getItem('shardflow_user_id') || 'default';

  const response = await fetch(`${API_BASE}/chat`, {
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

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${response.statusText}${errorBody ? ` - ${errorBody}` : ''}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEventType = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) { onDone(); break; }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim();
          continue;
        }
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent({ type: currentEventType || parsed.type || 'message', data: parsed.data || parsed });
            currentEventType = '';
          } catch { /* skip malformed */ }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      onDone();
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
  const { data } = await systemApi.get(`/shards/${taskId}/latest`);
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
  return data.data || data;
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
  return data.data || data;
}

export async function uploadKbDocument(
  collectionId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<KbDocument> {
  const formData = new FormData();
  formData.append('file', file);

  const token = localStorage.getItem('shardflow_token');
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
