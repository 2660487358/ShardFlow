import { create } from 'zustand';
import type { ChatMessage, Task, ContextShard, StrategyRecord, UserProfile } from '@/types';

interface McpTool {
  tool_id: string;
  tool_name: string;
  description: string;
  version: string;
  status: string;
  last_health_check?: string;
}

interface SessionSummary {
  id: string;
  session_seq: number;
  date: string;
  source_port: string;
  status: string;
  summary: string;
}

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
  currentShard: ContextShard | null;
  setShard: (shard: ContextShard | null) => void;

  // Strategies
  strategies: StrategyRecord[];
  setStrategies: (s: StrategyRecord[]) => void;

  // Auth
  token: string | null;
  userId: string;
  setAuth: (token: string, userId: string) => void;
  logout: () => void;

  // Profile (Phase 3)
  userProfile: UserProfile | null;
  profileLoading: boolean;
  setProfile: (p: UserProfile | null) => void;
  setProfileLoading: (v: boolean) => void;

  // MCP (Phase 3)
  mcpTools: McpTool[];
  mcpLoading: boolean;
  setMcpTools: (tools: McpTool[]) => void;
  setMcpLoading: (v: boolean) => void;

  // Sessions (Phase 3)
  sessionHistory: SessionSummary[];
  continuationContext: { taskId: string; summary: string } | null;
  setSessionHistory: (s: SessionSummary[]) => void;
  setContinuationContext: (c: { taskId: string; summary: string } | null) => void;

  // UI (Phase 3)
  theme: 'light' | 'dark';
  sidebarCollapsed: boolean;
  panelVisibility: Record<string, boolean>;
  setTheme: (t: 'light' | 'dark') => void;
  setSidebarCollapsed: (v: boolean) => void;
  setPanelVisibility: (key: string, v: boolean) => void;
}

export const useStore = create<AppState>((set) => ({
  // Chat
  messages: [],
  isStreaming: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  setStreaming: (v) => set({ isStreaming: v }),

  // Task
  tasks: [],
  activeTaskId: null,
  activeSessionId: null,
  setTasks: (tasks) => set({ tasks }),
  setActiveTask: (taskId, sessionId) => set({ activeTaskId: taskId, activeSessionId: sessionId || null }),

  // Shard
  currentShard: null,
  setShard: (shard) => set({ currentShard: shard }),

  // Strategies
  strategies: [],
  setStrategies: (s) => set({ strategies: s }),

  // Auth
  token: localStorage.getItem('shardflow_token') || '',
  userId: localStorage.getItem('shardflow_user_id') || '',
  setAuth: (token, userId) => {
    localStorage.setItem('shardflow_token', token);
    localStorage.setItem('shardflow_user_id', userId);
    set({ token, userId });
  },
  logout: () => {
    localStorage.removeItem('shardflow_token');
    localStorage.removeItem('shardflow_user_id');
    set({ token: null, userId: '' });
  },

  // Profile
  userProfile: null,
  profileLoading: false,
  setProfile: (p) => set({ userProfile: p }),
  setProfileLoading: (v) => set({ profileLoading: v }),

  // MCP
  mcpTools: [],
  mcpLoading: false,
  setMcpTools: (tools) => set({ mcpTools: tools }),
  setMcpLoading: (v) => set({ mcpLoading: v }),

  // Sessions
  sessionHistory: [],
  continuationContext: null,
  setSessionHistory: (s) => set({ sessionHistory: s }),
  setContinuationContext: (c) => set({ continuationContext: c }),

  // UI
  theme: 'light',
  sidebarCollapsed: false,
  panelVisibility: {},
  setTheme: (t) => set({ theme: t }),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  setPanelVisibility: (key, v) => set((s) => ({
    panelVisibility: { ...s.panelVisibility, [key]: v },
  })),
}));
