import { create } from 'zustand';
import type { ChatMessage, Task, ShardData, StrategyRecord } from '@/types';

interface AppState {
  // Chat
  messages: ChatMessage[];
  isStreaming: boolean;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  setStreaming: (v: boolean) => void;

  // Task
  tasks: Task[];
  activeTaskId: string | null;
  activeSessionId: string | null;
  setTasks: (tasks: Task[]) => void;
  setActiveTask: (taskId: string, sessionId?: string) => void;

  // Shard
  currentShard: ShardData | null;
  setShard: (shard: ShardData | null) => void;

  // Strategies
  strategies: StrategyRecord[];
  setStrategies: (s: StrategyRecord[]) => void;

  // Auth
  token: string | null;
  tenantId: string;
  setAuth: (token: string, tenantId: string) => void;
  logout: () => void;
}

export const useStore = create<AppState>((set) => ({
  messages: [],
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  setStreaming: (v) => set({ isStreaming: v }),

  tasks: [],
  activeTaskId: null,
  activeSessionId: null,
  setTasks: (tasks) => set({ tasks }),
  setActiveTask: (taskId, sessionId) => set({ activeTaskId: taskId, activeSessionId: sessionId || null }),

  currentShard: null,
  setShard: (shard) => set({ currentShard: shard }),

  strategies: [],
  setStrategies: (s) => set({ strategies: s }),

  token: localStorage.getItem('kb_token'),
  tenantId: localStorage.getItem('kb_tenant_id') || 'default',
  setAuth: (token, tenantId) => {
    localStorage.setItem('kb_token', token);
    localStorage.setItem('kb_tenant_id', tenantId);
    set({ token, tenantId });
  },
  logout: () => {
    localStorage.removeItem('kb_token');
    set({ token: null });
  },
}));
