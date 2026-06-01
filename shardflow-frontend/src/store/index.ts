import { create } from 'zustand';
import type { ChatMessage, Task, ContextShard, StrategyRecord, UserProfile, AgentConfig, CustomModel, KbCollection, KbMountState, KbSearchResult } from '@/types';

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
  abortController: AbortController | null;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  setStreaming: (v: boolean) => void;
  setAbortController: (c: AbortController | null) => void;

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

  // Knowledge Base
  kbCollections: KbCollection[];
  kbLoading: boolean;
  kbActiveMount: KbMountState;
  kbSearchResults: KbSearchResult[];
  setKbCollections: (collections: KbCollection[]) => void;
  setKbLoading: (v: boolean) => void;
  setKbActiveMount: (state: Partial<KbMountState>) => void;
  setKbSearchResults: (results: KbSearchResult[]) => void;
  clearKbSearchResults: () => void;

  // Custom Models
  customModels: CustomModel[];
  addCustomModel: (model: Omit<CustomModel, 'id' | 'created_at'>) => void;
  removeCustomModel: (id: string) => void;
  updateCustomModel: (id: string, updates: Partial<Omit<CustomModel, 'id' | 'created_at'>>) => void;
  setCustomModels: (models: CustomModel[]) => void;

  // Agent Configs
  agentConfigs: AgentConfig[];
  activeAgentId: string | null;
  addAgent: (agent: Omit<AgentConfig, 'id' | 'created_at' | 'updated_at'>) => void;
  removeAgent: (id: string) => void;
  updateAgent: (id: string, updates: Partial<Omit<AgentConfig, 'id' | 'created_at' | 'updated_at'>>) => void;
  setActiveAgent: (id: string | null) => void;
  setAgentConfigs: (configs: AgentConfig[]) => void;
}

export const useStore = create<AppState>((set) => ({
  // Chat
  messages: [],
  isStreaming: false,
  abortController: null,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  setStreaming: (v) => set({ isStreaming: v }),
  setAbortController: (c) => set({ abortController: c }),

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

  // Knowledge Base
  kbCollections: [],
  kbLoading: false,
  kbActiveMount: { mounted: false, collectionId: null, collectionName: '' },
  kbSearchResults: [],
  setKbCollections: (collections) => set({ kbCollections: collections }),
  setKbLoading: (v) => set({ kbLoading: v }),
  setKbActiveMount: (state) => set((s) => ({ kbActiveMount: { ...s.kbActiveMount, ...state } })),
  setKbSearchResults: (results) => set({ kbSearchResults: results }),
  clearKbSearchResults: () => set({ kbSearchResults: [] }),

  // Custom Models
  customModels: JSON.parse(localStorage.getItem('shardflow_custom_models') || '[]'),
  addCustomModel: (model) => set((s) => {
    const newModel: CustomModel = { ...model, id: `custom-${Date.now()}`, created_at: new Date().toISOString() };
    const updated = [...s.customModels, newModel];
    localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
    return { customModels: updated };
  }),
  removeCustomModel: (id) => set((s) => {
    const updated = s.customModels.filter((m) => m.id !== id);
    localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
    return { customModels: updated };
  }),
  updateCustomModel: (id, updates) => set((s) => {
    const updated = s.customModels.map((m) => m.id === id ? { ...m, ...updates } : m);
    localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
    return { customModels: updated };
  }),
  setCustomModels: (models) => set({ customModels: models }),

  // Agent Configs
  agentConfigs: JSON.parse(localStorage.getItem('shardflow_agents') || '[]'),
  activeAgentId: localStorage.getItem('shardflow_active_agent') || null,
  addAgent: (agent) => set((s) => {
    const now = new Date().toISOString();
    const newAgent: AgentConfig = { ...agent, id: `agent-${Date.now()}`, created_at: now, updated_at: now };
    const updated = [...s.agentConfigs, newAgent];
    localStorage.setItem('shardflow_agents', JSON.stringify(updated));
    return { agentConfigs: updated };
  }),
  removeAgent: (id) => set((s) => {
    const updated = s.agentConfigs.filter((a) => a.id !== id);
    localStorage.setItem('shardflow_agents', JSON.stringify(updated));
    if (s.activeAgentId === id) {
      localStorage.removeItem('shardflow_active_agent');
      return { agentConfigs: updated, activeAgentId: null };
    }
    return { agentConfigs: updated };
  }),
  updateAgent: (id, updates) => set((s) => {
    const updated = s.agentConfigs.map((a) => a.id === id ? { ...a, ...updates, updated_at: new Date().toISOString() } : a);
    localStorage.setItem('shardflow_agents', JSON.stringify(updated));
    return { agentConfigs: updated };
  }),
  setActiveAgent: (id) => {
    if (id) localStorage.setItem('shardflow_active_agent', id);
    else localStorage.removeItem('shardflow_active_agent');
    set({ activeAgentId: id });
  },
  setAgentConfigs: (configs) => set({ agentConfigs: configs }),
}));
