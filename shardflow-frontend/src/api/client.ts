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
  const userId = localStorage.getItem('shardflow_user_id');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (userId) config.headers['X-User-Id'] = userId;
  return config;
});

export default api;

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
        'X-User-Id': userId,
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
