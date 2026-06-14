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
    | 'profile_applied' | 'shard_resume' | 'kb_search' | 'done' | 'error'
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
  kbSearchResults?: KbSearchResult[];  // Knowledge base search results for this message
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
  document_code?: string;
  collection_id: string;
  user_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  minio_url?: string;
  parse_strategy?: string;
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

// ── MCP Tool Types ──

export interface McpTool {
  toolId: string;
  toolName: string;
  toolType: 'BUILTIN' | 'MCP';
  description: string;
  category: string;
  tags: string[];
  mcpServerUrl: string;
  transport: string;
  healthCheckUrl: string;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown>;
  permissions: string[];
  riskLevel: string;
  version: string;
  timeoutSeconds: number;
  retryCount: number;
  authConfigType: string;
  status: 'DRAFT' | 'ACTIVE' | 'INACTIVE';
  healthStatus: 'HEALTHY' | 'UNHEALTHY' | 'UNKNOWN';
  lastHealthCheckAt: string;
  ownerTeam: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface McpToolSummary {
  toolId: string;
  toolName: string;
  toolType: 'BUILTIN' | 'MCP';
  description: string;
  category: string;
  tags: string[];
  version: string;
  status: 'DRAFT' | 'ACTIVE' | 'INACTIVE';
  healthStatus: 'HEALTHY' | 'UNHEALTHY' | 'UNKNOWN';
  permissions: string[];
  mcpServerUrl: string;
  transport: string;
  riskLevel: string;
  ownerTeam: string;
  createdAt: string;
  updatedAt: string;
}

export interface McpToolListResult {
  tools: McpToolSummary[];
  total: number;
  page: number;
  size: number;
}

export interface McpToolRegisterRequest {
  toolName: string;
  description: string;
  category?: string;
  tags?: string[];
  mcpServerUrl?: string;
  transport?: string;
  healthCheckUrl?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  permissions?: string[];
  riskLevel?: string;
  version: string;
  timeoutSeconds?: number;
  retryCount?: number;
  authConfig?: {
    type: string;
    tokenKey?: string;
    keyName?: string;
    keyValueEnv?: string;
    clientIdEnv?: string;
    clientSecretEnv?: string;
    tokenUrl?: string;
  };
  ownerTeam?: string;
  metadata?: Record<string, unknown>;
}

export interface McpHealthCheckResult {
  toolId: string;
  toolName: string;
  healthStatus: 'HEALTHY' | 'UNHEALTHY' | 'UNKNOWN';
  lastHealthCheckAt: string;
  consecutiveFailures: number;
  consecutiveSuccesses: number;
  message: string;
  latencyMs: number;
}

export interface McpVersionEntry {
  id: number;
  version: string;
  description: string;
  changelog: string;
  status: string;
  createdAt: string;
  createdBy: string;
}

export interface McpVersionResult {
  toolId: string;
  toolName: string;
  currentVersion: string;
  versions: McpVersionEntry[];
}

export interface McpMetadataAuditEntry {
  id: number;
  userId: string;
  operator: string;
  toolId: string;
  toolName: string;
  operationType: string;
  changeSummary: string;
  operationAt: string;
}

export interface McpCallAuditEntry {
  id: number;
  traceId: string;
  spanId: string;
  userId: string;
  sessionId: string;
  toolId: string;
  toolName: string;
  toolVersion: string;
  inputParams: string;
  outputPreview: string;
  status: string;
  errorCode: string;
  errorMsg: string;
  latencyMs: number;
  requestAt: string;
}

export interface McpAuditLogResult {
  logs: McpMetadataAuditEntry[] | McpCallAuditEntry[];
  total: number;
  page: number;
  size: number;
}
