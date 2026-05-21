// Core types for KnowledgeBridge frontend

export interface ConversationRequest {
  task_id: string;
  message: string;
  session_id?: string;
  tenant_id?: string;
  stream?: boolean;
}

export interface SSEEvent {
  type: 'intent' | 'think' | 'action' | 'observe' | 'shard_trigger' | 'shard_result' | 'strategy' | 'progress' | 'done' | 'error';
  data: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  eventType?: SSEEvent['type'];
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

export interface ShardData {
  task_id: string;
  tenant_id: string;
  session_seq: number;
  confirmed: Array<{ fact: string; confidence: number; evidence?: string[] }>;
  excluded: Array<{ hypothesis: string; reason: string }>;
  pending: string[];
  exploration_depth: string;
  key_decisions: Array<{ decision: string; reason: string; confidence: number }>;
  version: number;
  status: string;
}

export interface StrategyRecord {
  strategy_id: string;
  task_type: string;
  query_pattern: string;
  success_score: number;
  cost_ms: number;
}
