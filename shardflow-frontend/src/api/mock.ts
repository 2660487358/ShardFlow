import type { Task, SSEEvent } from '@/types';

export const mockTasks: Task[] = [
  {
    task_id: 'task-demo-001',
    title: '理清 Dubbo 注册链路',
    status: 'RUNNING',
    session_id: 'session-demo-001',
    created_at: new Date().toISOString(),
  },
  {
    task_id: 'task-demo-002',
    title: '分析 Spring Cloud Gateway 鉴权',
    status: 'PENDING',
    session_id: 'session-demo-002',
    created_at: new Date().toISOString(),
  },
  {
    task_id: 'task-demo-003',
    title: '排查 Redis 连接池耗尽',
    status: 'COMPLETED',
    session_id: 'session-demo-003',
    created_at: new Date().toISOString(),
  },
];

export const mockSSEEvents: SSEEvent[] = [
  {
    type: 'intent',
    data: { intent: 'code_exploration', confidence: 0.92 },
  },
  {
    type: 'think',
    data: { reasoning: '用户希望理清 Dubbo 注册链路。我需要从服务注册入口开始，追踪 RegistryProtocol → ZookeeperRegistry → 节点创建的完整路径。首先搜索 RegistryProtocol 的 export 方法。' },
  },
  {
    type: 'action',
    data: { tool: 'search_code', params: { query: 'RegistryProtocol export', scope: 'dubbo-registry' } },
  },
  {
    type: 'observe',
    data: { result: '找到 RegistryProtocol.java，export() 方法在第 145 行调用 registry.register()，注册 URL 到注册中心。' },
  },
  {
    type: 'progress',
    data: { loop: 1, context_usage: 0.25 },
  },
  {
    type: 'think',
    data: { reasoning: '已确认注册入口。接下来需要追踪 registry.register() 的具体实现，查看 ZookeeperRegistry 如何创建节点。' },
  },
  {
    type: 'action',
    data: { tool: 'read_file', params: { path: 'ZookeeperRegistry.java', lines: '80-120' } },
  },
  {
    type: 'observe',
    data: { result: 'ZookeeperRegistry.doRegister() 在第 95 行调用 zkClient.create()，创建临时节点 /dubbo/{service}/providers/{url}。' },
  },
  {
    type: 'progress',
    data: { loop: 2, context_usage: 0.45 },
  },
  {
    type: 'answer',
    data: { content: 'Dubbo 注册链路：ServiceConfig.export() → RegistryProtocol.export() → registry.register(url) → ZookeeperRegistry.doRegister() → zkClient.createEphemeral()。服务以临时节点形式注册到 Zookeeper 的 /dubbo/{service}/providers/ 路径下。' },
  },
  {
    type: 'done',
    data: { answer: 'Dubbo 注册链路：ServiceConfig.export() → RegistryProtocol.export() → registry.register(url) → ZookeeperRegistry.doRegister() → zkClient.createEphemeral()。服务以临时节点形式注册到 Zookeeper 的 /dubbo/{service}/providers/ 路径下。' },
  },
];
