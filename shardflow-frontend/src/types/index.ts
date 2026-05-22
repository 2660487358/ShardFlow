// Core types for ShardFlow frontend

export interface ConversationRequest {
  task_id: string;
  message: string;
  session_id?: string;
  user_id?: string;
  stream?: boolean;
}

export interface SSEEvent {
  type: 'profile_applied' | 'message' | 'tool_call_start' | 'tool_call_result'
    | 'strategy_found' | 'done' | 'error'
    // Legacy mock types
    | 'intent' | 'think' | 'action' | 'observe' | 'shard_trigger' | 'shard_result' | 'strategy' | 'progress';
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

export interface ShardData {
  task_id: string;
  user_id: string;
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
