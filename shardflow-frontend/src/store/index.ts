import { create } from 'zustand';
import type { ChatMessage, Task, AgentConfig, CustomModel, KbCollection, KbMountState, KbSearchResult, StreamingPhase } from '@/types';

// Lazy API imports to avoid circular deps (client.ts imports useStore)
const api = {
  fetchCustoms: () => import('@/api/client').then(m => m.fetchCustomModels()),
  addCustom: (p: Record<string, unknown>) => import('@/api/client').then(m => m.addCustomModelApi(p)),
  updateCustom: (id: string, p: Record<string, unknown>) => import('@/api/client').then(m => m.updateCustomModelApi(id, p)),
  deleteCustom: (id: string) => import('@/api/client').then(m => m.deleteCustomModelApi(id)),
  fetchAgents: () => import('@/api/client').then(m => m.fetchAgentConfigs()),
  addAgent: (p: Record<string, unknown>) => import('@/api/client').then(m => m.addAgentConfigApi(p)),
  updateAgent: (id: string, p: Record<string, unknown>) => import('@/api/client').then(m => m.updateAgentConfigApi(id, p)),
  deleteAgent: (id: string) => import('@/api/client').then(m => m.deleteAgentConfigApi(id)),
};

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
  streamingPhase: StreamingPhase;
  abortController: AbortController | null;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  setStreaming: (v: boolean) => void;
  setStreamingPhase: (phase: StreamingPhase) => void;
  setAbortController: (c: AbortController | null) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;

  // Context pressure
  contextPressure: { level: string; usage_ratio: number; message: string } | null;
  setContextPressure: (p: { level: string; usage_ratio: number; message: string } | null) => void;
  contextSwitchPreview: boolean;
  setContextSwitchPreview: (v: boolean) => void;

  // Task
  tasks: Task[];
  activeTaskId: string | null;
  activeSessionId: string | null;
  setTasks: (tasks: Task[]) => void;
  setActiveTask: (taskId: string, sessionId?: string) => void;

  // Auth
  token: string | null;
  userId: string;
  setAuth: (token: string, userId: string, refreshToken?: string, expiresIn?: number) => void;
  logout: () => void;

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
  syncCustomModels: () => Promise<void>;

  // Agent Configs
  agentConfigs: AgentConfig[];
  activeAgentId: string | null;
  addAgent: (agent: Omit<AgentConfig, 'id' | 'created_at' | 'updated_at'>) => void;
  removeAgent: (id: string) => void;
  updateAgent: (id: string, updates: Partial<Omit<AgentConfig, 'id' | 'created_at' | 'updated_at'>>) => void;
  setActiveAgent: (id: string | null) => void;
  setAgentConfigs: (configs: AgentConfig[]) => void;
  syncAgentConfigs: () => Promise<void>;
}

export const useStore = create<AppState>((set) => ({
  // Chat
  messages: [],
  isStreaming: false,
  streamingPhase: 'idle' as StreamingPhase,
  abortController: null,
  contextPressure: null,
  contextSwitchPreview: (() => {
    try { return localStorage.getItem('shardflow_context_switch_preview') === 'true'; }
    catch { return false; }
  })(),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  clearMessages: () => set({ messages: [] }),
  setStreaming: (v) => set({ isStreaming: v }),
  setStreamingPhase: (phase) => set({ streamingPhase: phase }),
  setAbortController: (c) => set({ abortController: c }),
  setContextPressure: (p) => set({ contextPressure: p }),
  setContextSwitchPreview: (v) => {
    try { localStorage.setItem('shardflow_context_switch_preview', String(v)); } catch {}
    set({ contextSwitchPreview: v });
  },
  updateMessage: (id, updates) => set((s) => ({
    messages: s.messages.map((m) => m.id === id ? { ...m, ...updates } : m),
  })),

  // Task
  tasks: [],
  activeTaskId: null,
  activeSessionId: null,
  setTasks: (tasks) => set({ tasks }),
  setActiveTask: (taskId, sessionId) => set({ activeTaskId: taskId, activeSessionId: sessionId || null }),

  // Auth — validate stored token looks like JWT before accepting it
  token: (() => {
    const t = localStorage.getItem('shardflow_token') || '';
    if (t && !t.startsWith('eyJ')) {
      localStorage.removeItem('shardflow_token');
      localStorage.removeItem('shardflow_refresh_token');
      localStorage.removeItem('shardflow_user_id');
      localStorage.removeItem('shardflow_token_expires_at');
      return '';
    }
    return t;
  })(),
  userId: localStorage.getItem('shardflow_user_id') || '',
  setAuth: (token, userId, refreshToken?: string, expiresIn?: number) => {
    localStorage.setItem('shardflow_token', token);
    localStorage.setItem('shardflow_user_id', userId);
    if (refreshToken) {
      localStorage.setItem('shardflow_refresh_token', refreshToken);
    }
    if (expiresIn) {
      localStorage.setItem('shardflow_token_expires_at', String(Date.now() + expiresIn * 1000));
    }
    set({ token, userId });
    // 登录后调度主动刷新
    import('@/api/client').then(({ scheduleProactiveRefresh }) => {
      scheduleProactiveRefresh();
    });
  },
  logout: () => {
    const refreshToken = localStorage.getItem('shardflow_refresh_token');
    const token = localStorage.getItem('shardflow_token');
    localStorage.removeItem('shardflow_token');
    localStorage.removeItem('shardflow_refresh_token');
    localStorage.removeItem('shardflow_user_id');
    localStorage.removeItem('shardflow_token_expires_at');
    localStorage.removeItem('shardflow_custom_models');
    localStorage.removeItem('shardflow_agents');
    localStorage.removeItem('shardflow_active_agent');
    localStorage.removeItem('shardflow_selected_model');
    set({ token: null, userId: '', customModels: [], agentConfigs: [], activeAgentId: null });
    // 通知后端注销双 token
    if (token) {
      import('@/api/client').then(({ default: api }) => {
        api.post('/logout', { refresh_token: refreshToken || '' }).catch(() => {});
      });
    }
  },

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
  setKbCollections: (collections) => set({ kbCollections: Array.isArray(collections) ? collections : [] }),
  setKbLoading: (v) => set({ kbLoading: v }),
  setKbActiveMount: (state) => set((s) => ({ kbActiveMount: { ...s.kbActiveMount, ...state } })),
  setKbSearchResults: (results) => set({ kbSearchResults: results }),
  clearKbSearchResults: () => set({ kbSearchResults: [] }),

  // Custom Models
  customModels: JSON.parse(localStorage.getItem('shardflow_custom_models') || '[]'),
  addCustomModel: (model) => {
    const tempId = `custom-${Date.now()}`;
    const newModel: CustomModel = { ...model, id: tempId, created_at: new Date().toISOString() };
    // Optimistic update
    set((s) => {
      const updated = [...s.customModels, newModel];
      localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
      return { customModels: updated };
    });
    // API call — update with real server data on success, rollback on failure
    api.addCustom(newModel as unknown as Record<string, unknown>).then((resp: unknown) => {
      const serverModel = resp as Record<string, unknown> | null;
      if (serverModel && (serverModel.id != null || serverModel.model_code != null)) {
        // Replace temp ID with server-generated id/model_code
        set((s) => {
          const updated = s.customModels.map((m) =>
            m.id === tempId
              ? { ...m, id: String(serverModel.id ?? m.id), model_code: serverModel.model_code as string | undefined, ...serverModel }
              : m
          );
          localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
          return { customModels: updated };
        });
      }
      import('antd').then(({ message }) => { message.success('模型添加成功'); });
    }).catch((err: Error) => {
      set((s) => {
        const rolled = s.customModels.filter((m) => m.id !== tempId);
        localStorage.setItem('shardflow_custom_models', JSON.stringify(rolled));
        return { customModels: rolled };
      });
      import('antd').then(({ message }) => {
        message.error(`模型保存失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  removeCustomModel: (id) => {
    const removed = useStore.getState().customModels.find((m) => m.id === id);
    // Optimistic update
    set((s) => {
      const updated = s.customModels.filter((m) => m.id !== id);
      localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
      return { customModels: updated };
    });
    api.deleteCustom(id).then(() => {
      import('antd').then(({ message }) => { message.success('模型删除成功'); });
    }).catch((err: Error) => {
      // Rollback on failure
      if (removed) {
        set((s) => {
          const restored = [...s.customModels, removed];
          localStorage.setItem('shardflow_custom_models', JSON.stringify(restored));
          return { customModels: restored };
        });
      }
      import('antd').then(({ message }) => {
        message.error(`模型删除失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  updateCustomModel: (id, updates) => {
    // Snapshot previous state for rollback
    const prev = useStore.getState().customModels.find((m) => m.id === id);
    // Optimistic update
    set((s) => {
      const updated = s.customModels.map((m) => m.id === id ? { ...m, ...updates } : m);
      localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
      return { customModels: updated };
    });
    api.updateCustom(id, updates as Record<string, unknown>).then((resp: unknown) => {
      const serverModel = resp as Record<string, unknown> | null;
      if (serverModel) {
        // Sync server-returned fields (e.g. is_verified, updated api_key_id)
        set((s) => {
          const updated = s.customModels.map((m) =>
            m.id === id ? { ...m, ...serverModel } : m
          );
          localStorage.setItem('shardflow_custom_models', JSON.stringify(updated));
          return { customModels: updated };
        });
      }
      import('antd').then(({ message }) => { message.success('模型更新成功'); });
    }).catch((err: Error) => {
      // Rollback to previous state
      if (prev) {
        set((s) => {
          const rolled = s.customModels.map((m) => m.id === id ? prev : m);
          localStorage.setItem('shardflow_custom_models', JSON.stringify(rolled));
          return { customModels: rolled };
        });
      }
      import('antd').then(({ message }) => {
        message.error(`模型更新失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  setCustomModels: (models) => set({ customModels: models }),
  syncCustomModels: async () => {
    try {
      const data = await api.fetchCustoms();
      if (Array.isArray(data)) {
        set({ customModels: data as CustomModel[] });
        localStorage.setItem('shardflow_custom_models', JSON.stringify(data));
      } else {
        // 服务端返回非数组（如空对象），清除缓存
        set({ customModels: [] });
        localStorage.removeItem('shardflow_custom_models');
      }
    } catch {
      // API 不可用时保留 localStorage 数据作为降级
      // 但如果是 401，handleAuthExpired 已经清除了缓存
    }
  },

  // Agent Configs
  agentConfigs: JSON.parse(localStorage.getItem('shardflow_agents') || '[]'),
  activeAgentId: localStorage.getItem('shardflow_active_agent') || null,
  addAgent: (agent) => {
    const now = new Date().toISOString();
    const newAgent: AgentConfig = { ...agent, id: `agent-${Date.now()}`, created_at: now, updated_at: now };
    // Optimistic update
    set((s) => {
      const updated = [...s.agentConfigs, newAgent];
      localStorage.setItem('shardflow_agents', JSON.stringify(updated));
      return { agentConfigs: updated };
    });
    api.addAgent(newAgent as unknown as Record<string, unknown>).catch((err: Error) => {
      set((s) => {
        const rolled = s.agentConfigs.filter((a) => a.id !== newAgent.id);
        localStorage.setItem('shardflow_agents', JSON.stringify(rolled));
        return { agentConfigs: rolled };
      });
      import('antd').then(({ message }) => {
        message.error(`Agent 保存失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  removeAgent: (id) => {
    const removed = useStore.getState().agentConfigs.find((a) => a.id === id);
    // Optimistic update
    set((s) => {
      const updated = s.agentConfigs.filter((a) => a.id !== id);
      localStorage.setItem('shardflow_agents', JSON.stringify(updated));
      if (s.activeAgentId === id) {
        localStorage.removeItem('shardflow_active_agent');
        return { agentConfigs: updated, activeAgentId: null };
      }
      return { agentConfigs: updated };
    });
    api.deleteAgent(id).catch((err: Error) => {
      // Rollback on failure
      if (removed) {
        set((s) => {
          const restored = [...s.agentConfigs, removed];
          localStorage.setItem('shardflow_agents', JSON.stringify(restored));
          return { agentConfigs: restored, activeAgentId: s.activeAgentId };
        });
      }
      import('antd').then(({ message }) => {
        message.error(`Agent 删除失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  updateAgent: (id, updates) => {
    const prev = useStore.getState().agentConfigs.find((a) => a.id === id);
    set((s) => {
      const updated = s.agentConfigs.map((a) => a.id === id ? { ...a, ...updates, updated_at: new Date().toISOString() } : a);
      localStorage.setItem('shardflow_agents', JSON.stringify(updated));
      return { agentConfigs: updated };
    });
    api.updateAgent(id, updates as Record<string, unknown>).catch((err: Error) => {
      if (prev) {
        set((s) => {
          const rolled = s.agentConfigs.map((a) => a.id === id ? prev : a);
          localStorage.setItem('shardflow_agents', JSON.stringify(rolled));
          return { agentConfigs: rolled };
        });
      }
      import('antd').then(({ message }) => {
        message.error(`Agent 更新失败: ${err?.message || '请检查后端服务是否可用'}`);
      });
    });
  },
  setActiveAgent: (id) => {
    if (id) localStorage.setItem('shardflow_active_agent', id);
    else localStorage.removeItem('shardflow_active_agent');
    set({ activeAgentId: id });
  },
  setAgentConfigs: (configs) => set({ agentConfigs: configs }),
  syncAgentConfigs: async () => {
    try {
      const data = await api.fetchAgents();
      if (Array.isArray(data)) {
        set({ agentConfigs: data as AgentConfig[] });
        localStorage.setItem('shardflow_agents', JSON.stringify(data));
      }
    } catch { /* API unavailable, keep localStorage data */ }
  },
}));
