// 知识库 API 服务
import apiClient from './api';

export interface KnowledgeDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface SearchResult {
  id: string;
  content: string;
  filename: string;
  similarity: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
}

export interface DocumentListResponse {
  documents: KnowledgeDocument[];
  total: number;
}

export const knowledgeApi = {
  // 上传文档
  async uploadDocument(file: File): Promise<KnowledgeDocument> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<KnowledgeDocument>('/knowledge/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // 列出所有文档
  async listDocuments(): Promise<DocumentListResponse> {
    const response = await apiClient.get<DocumentListResponse>('/knowledge/documents');
    return response.data;
  },

  // 根据 ID 获取文档
  async getDocument(id: string): Promise<KnowledgeDocument> {
    const response = await apiClient.get<KnowledgeDocument>(`/knowledge/documents/${id}`);
    return response.data;
  },

  // 删除文档
  async deleteDocument(id: string): Promise<void> {
    await apiClient.delete(`/knowledge/documents/${id}`);
  },

  // 搜索知识库
  async search(
    query: string,
    options?: {
      top_k?: number;
      mode?: 'hybrid' | 'semantic' | 'keyword';
    }
  ): Promise<SearchResponse> {
    const response = await apiClient.post<SearchResponse>('/knowledge/search', {
      query,
      top_k: options?.top_k ?? 5,
      mode: options?.mode ?? 'hybrid',
    });
    return response.data;
  },
};

export default knowledgeApi;
