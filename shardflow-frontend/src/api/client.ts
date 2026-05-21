import axios from 'axios';

const API_BASE = '/agent/v1';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor: inject tenant/session headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('kb_token');
  const tenantId = localStorage.getItem('kb_tenant_id') || 'default';
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers['X-Tenant-Id'] = tenantId;
  return config;
});

export default api;

// --------------- API functions ---------------

export async function sendConversation(
  taskId: string,
  message: string,
  sessionId: string,
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
  onError: (err: Error) => void,
  onDone: () => void,
): Promise<void> {
  const token = localStorage.getItem('kb_token') || '';
  const tenantId = localStorage.getItem('kb_tenant_id') || 'default';

  try {
    const response = await fetch(`${API_BASE}/conversation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'X-Tenant-Id': tenantId,
      },
      body: JSON.stringify({
        task_id: taskId,
        message,
        session_id: sessionId,
        tenant_id: tenantId,
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

    while (true) {
      const { done, value } = await reader.read();
      if (done) { onDone(); break; }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          const eventType = line.slice(7).trim();
          // Next line should be data:
          continue;
        }
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6));
            onEvent(parsed);
          } catch { /* skip malformed */ }
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

export async function fetchTasks(): Promise<unknown[]> {
  const { data } = await api.get('/sessions');
  return data.sessions || data;
}

export async function createTask(title: string): Promise<{ task_id: string }> {
  const { data } = await api.post('/sessions', { title });
  return data;
}

export async function fetchShard(taskId: string): Promise<unknown> {
  const { data } = await api.get(`/sessions/${taskId}/shards`);
  return data;
}
