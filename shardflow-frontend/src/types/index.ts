// Core types for ShardFlow frontend

export interface ConversationRequest {
  task_id: string;
  message: string;
  session_id?: string;
  user_id?: string;
  stream?: boolean;
}

export interface SSEEvent {
  type: 'intent' | 'think' | 'answer' | 'action' | 'observe' | 'progress'
    | 'shard_trigger' | 'shard_result' | 'strategy'
    | 'profile_applied' | 'shard_resume' | 'done' | 'error'
    | 'heartbeat';
  data: Record<string, unknown>;
}

export type StreamingPhase = 'idle' | 'thinking' | 'answering' | 'done';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  eventType?: SSEEvent['type'];
  thinkingContent?: string;  // Raw think tokens for collapsible display
  streamingPhase?: StreamingPhase;  // Current streaming phase
  timestamp: number;
}

export interface Task {
  task_id: string;
  title: string;
  description?: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  session_id?: string;
  created_at?: string;
}

// Aligned with Python models/context_shard.py
export interface ContextShard {
  task_id: string;
  user_id: string;
  task_type: string;
  task_goal: string;
  knowledge_state: {
    confirmed: Array<{ fact: string; confidence: number; evidence?: string[] }>;
    excluded: Array<{ hypothesis: string; reason: string }>;
    pending: string[];
    key_decisions: Array<{ decision: string; reason: string; confidence: number }>;
  };
  user_context: {
    expertise_level: string;
    preferred_depth: string;
    communication_style: string;
  };
  execution_state: {
    progress: number;
    completed_steps: string[];
    tools_used: string[];
  };
  source_preference: Record<string, number>;
  version: number;
  status: string;
}

// Aligned with Python models/user_profile.py
export interface UserProfile {
  user_id: string;
  preferences: {
    communication_style: string;
    preferred_depth: string;
    preferred_sources: Record<string, number>;
  };
  expertise: {
    level: string;
    domains: string[];
    tech_stack: string[];
  };
  habits: {
    common_task_types: string[];
    peak_hours: string[];
    avg_session_duration_min: number;
  };
  updated_at: string;
}

export interface StrategyRecord {
  strategy_id: string;
  task_type: string;
  query_pattern: string;
  success_score: number;
  cost_ms: number;
}

// ── custom model types ──

export interface CustomModel {
  id: string;
  model_code?: string;
  name: string;
  provider: string;
  base_url?: string;
  model: string;
  api_key_id: string;
  api_key_encrypted?: string;
  capabilities?: string[];
  context_window?: number;
  enabled: boolean;
  is_verified?: boolean;
  created_at: string;
}

export interface AvailableModel {
  key: string;
  label: string;
  provider: string;
  model?: string;
  capabilities?: string;
  context_window?: number;
  type: 'builtin' | 'custom';
  is_verified?: boolean;
}

export interface AgentConfig {
  id: string;
  user_id: string;
  model_id: string;
  name: string;
  description: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  tools: string[];
  created_at: string;
  updated_at: string;
}

// ── Knowledge Base Types ──

export interface KbCollection {
  id: string;
  user_id: string;
  name: string;
  description: string;
  icon: string;
  status: 'ACTIVE' | 'ARCHIVED';
  doc_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KbDocument {
  id: string;
  collection_id: string;
  user_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  status: 'PENDING' | 'PARSING' | 'EMBEDDING' | 'READY' | 'ERROR';
  error_msg?: string;
  created_at: string;
}

export interface KbSearchResult {
  source: 'knowledge_base';
  title: string;
  snippet: string;
  url: string;
  relevance_score: number;
  metadata: {
    document_id: string;
    collection_name: string;
    chunk_index: number;
    node_id: string;
  };
}

export interface KbMountState {
  mounted: boolean;
  collectionId: string | null;
  collectionName: string;
}
