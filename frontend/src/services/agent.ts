// Agent API 服务
import apiClient from './api';
import type { AgentRequest, AgentResponse } from '@/types/agent';

export const agentService = {
  // 执行 agent 任务（阻塞）
  async run(request: AgentRequest): Promise<AgentResponse> {
    const { data } = await apiClient.post<AgentResponse>('/agent/run', request);
    return data;
  },

  // 健康检查
  async health(): Promise<{ status: string }> {
    const { data } = await apiClient.get('/health');
    return data;
  },

  // 获取可用工具
  async getTools(): Promise<any> {
    const { data } = await apiClient.get('/tools/');
    return data;
  },
};
