import axios from 'axios';
import { ElMessage } from 'element-plus';

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000
});

// 添加请求拦截器，自动附加认证token
apiClient.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 添加响应拦截器，处理token过期情况
apiClient.interceptors.response.use(
  response => {
    return response;
  },
  error => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('userInfo');
      ElMessage.error('登录已过期，请重新登录');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// 检测配置相关 API
export const detectionConfigApi = {
  // 获取检测配置列表
  getConfigs(params = { skip: 0, limit: 100 }, frequency) {
    const queryParams = { ...(params || { skip: 0, limit: 100 }) };
    if (frequency) {
      queryParams.frequency = frequency;
    }
    const filteredParams = Object.fromEntries(
      Object.entries(queryParams).filter(([_, value]) => value !== null && value !== undefined && value !== '')
    );
    return apiClient.get('/detection/configs', { params: filteredParams });
  },

  // 获取检测配置统计概览
  getConfigsStatsOverview() {
    return apiClient.get('/detection/configs/stats');
  },
  
  // 获取单个检测配置
  getConfig(configId) {
    return apiClient.get(`/detection/configs/${configId}`);
  },
  
  // 创建检测配置
  createConfig(configData) {
    return apiClient.post('/detection/configs', configData);
  },
  
  // 更新检测配置
  updateConfig(configId, configData) {
    return apiClient.put(`/detection/configs/${configId}`, configData);
  },
  
  // 删除检测配置
  deleteConfig(configId) {
    return apiClient.delete(`/detection/configs/${configId}`);
  },
  
  // 切换配置启用状态
  toggleConfig(configId, enabled) {
    return apiClient.put(`/detection/configs/${configId}/toggle?enabled=${enabled}`);
  }
};

// 检测事件相关 API
export const detectionEventApi = {
  // 获取检测事件列表
  getEvents(params = { skip: 0, limit: 100 }) {
    return apiClient.get('/detection/events', { params });
  },
  
  // 获取单个检测事件
  getEvent(eventId) {
    return apiClient.get(`/detection/events/${eventId}`);
  },

  async fetchThumbnail(eventId) {
    try {
        const response =await apiClient.get(`/detection/events/${eventId}/thumbnail`, {
            responseType: 'arraybuffer' // 确保响应类型为 blob
        });

        const base64 = btoa(
          new Uint8Array(response.data).reduce(
              (data, byte) => data + String.fromCharCode(byte),
              ''
          )
      );
      return `data:image/jpeg;base64,${base64}`;
    } catch (error) {
        throw error; // 抛出错误以便后续处理
    }
  },
  
  // 更新事件状态
  updateEventStatus(eventId, status) {
    return apiClient.put(`/detection/events/${eventId}`, { status });
  },
  
  // 更新事件备注
  updateEventNotes(eventId, notes) {
    return apiClient.put(`/detection/events/${eventId}`, { notes });
  },
  
  // 删除检测事件
  deleteEvent(eventId) {
    return apiClient.delete(`/detection/events/${eventId}`);
  },
  
  // 批量删除检测事件
  batchDeleteEvents(eventIds) {
    return apiClient.post('/detection/events/batch-delete', {
      event_ids: eventIds
    });
  },
  
  // 批量更新事件状态
  batchUpdateStatus(eventIds, status) {
    return apiClient.put('/detection/events/batch-update', {
      event_ids: eventIds,
      status: status
    });
  },

  // 获取检测事件统计概览
  getEventsStatsOverview() {
    return apiClient.get('/detection/stats');
  }
};