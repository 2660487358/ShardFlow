import axios from 'axios';
import { mockTasks, mockShard, mockSSEEvents } from './mock';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/agent/v1';
const AUTH_BASE = import.meta.env.VITE_AUTH_BASE_URL || '';

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
  baseURL: '/api/v1',
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

export async function login(username: string, password: string): Promise<{ token: string; refresh_token: string; expires_in: number }> {
  const { data } = await authApi.post('/auth/login', { username, password });
  return data;
}

export async function sendConversation(
  taskId: string,
  message: string,
  sessionId: string,
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
  onError: (err: Error) => void,
  onDone: () => void,
): Promise<void> {
  const token = localStorage.getItem('shardflow_token');
  const userId = localStorage.getItem('shardflow_user_id') || 'default';

  try {
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
        stream: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEventType = '';

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
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    if (error.message.includes('HTTP') || error.message.includes('fetch') || error.message.includes('Failed')) {
      replayMockSSE(onEvent, onDone);
    } else {
      onError(error);
    }
  }
}

export async function fetchTasks(): Promise<unknown[]> {
  try {
    const { data } = await api.get('/sessions');
    return data.sessions || data;
  } catch {
    return mockTasks;
  }
}

export async function createTask(title: string): Promise<{ task_id: string }> {
  try {
    const { data } = await api.post('/sessions', { title });
    return data;
  } catch {
    const taskId = `task-${Date.now()}`;
    return { task_id: taskId };
  }
}

export async function fetchShard(taskId: string): Promise<unknown> {
  try {
    const { data } = await api.get(`/sessions/${taskId}/shards`);
    return data;
  } catch {
    return mockShard;
  }
}

function replayMockSSE(
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
  onDone: () => void,
): void {
  let index = 0;
  const interval = setInterval(() => {
    if (index >= mockSSEEvents.length) {
      clearInterval(interval);
      onDone();
      return;
    }
    const event = mockSSEEvents[index];
    onEvent({ type: event.type, data: event.data });
    index++;
  }, 600);
}

// ── Knowledge Base API ──

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
    baseURL: import.meta.env.VITE_SF_SYSTEM_BASE_URL || '/api/v1',
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
