import axios from 'axios';
import { ElMessage } from 'element-plus';

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000
});

apiClient.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => Promise.reject(error)
);

apiClient.interceptors.response.use(
  response => response,
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

export const smartSchemeApi = {
  createScheme: (data) => apiClient.post('/smart-schemes/manager', data),
  getSchemes: (params) => apiClient.get('/smart-schemes/manager', { params }),
  getScheme: (schemeId) => apiClient.get(`/smart-schemes/manager/${schemeId}`),
  updateScheme: (schemeId, data) => apiClient.put(`/smart-schemes/manager/${schemeId}`, data),
  deleteScheme: (schemeId) => apiClient.delete(`/smart-schemes/manager/${schemeId}`),

  startScheme: (schemeId) => apiClient.post(`/smart-schemes/manager/${schemeId}/start`),
  stopScheme: (schemeId) => apiClient.post(`/smart-schemes/manager/${schemeId}/stop`),
  restartScheme: (schemeId) => apiClient.post(`/smart-schemes/manager/${schemeId}/restart`),

  getAllStatus: () => apiClient.get('/smart-schemes/status'),
  getSchemeStatus: (schemeId) => apiClient.get(`/smart-schemes/${schemeId}/status`),
  getSystemStatus: () => apiClient.get('/smart-schemes/system/status'),

  getSmartEvents: (params) => apiClient.get('/smart-schemes/events', { params }),
  getSmartEvent: (eventId) => apiClient.get(`/smart-schemes/events/${eventId}`),

  deleteSmartEvent: (eventId) => apiClient.delete(`/smart-schemes/events/${eventId}`),
  batchDeleteSmartEvents: (eventIds) => apiClient.post('/smart-schemes/events/batch-delete', { event_ids: eventIds }),

  batchProcessSmartEvents: (eventIds) => apiClient.post('/smart-schemes/events/batch-process', { event_ids: eventIds }),
  batchIgnoreSmartEvents: (eventIds) => apiClient.post('/smart-schemes/events/batch-ignore', { event_ids: eventIds }),

  getStats: () => apiClient.get('/smart-schemes/stats/summary'),
  getEventsStatsOverview: () => apiClient.get('/smart-schemes/stats/overview'),

  updateSmartEvent: (eventId, updateData) => apiClient.put(`/smart-schemes/events/${eventId}`, updateData),

  getCameras: () => apiClient.get('/smart-schemes/cameras'),
  getEventTypes: () => apiClient.get('/smart-schemes/event-types'),

  exportEvents: (params) => apiClient.get('/smart-schemes/events/export', {
    params,
    responseType: 'blob'
  }),

  getSchemeLogs: (schemeId, params) => apiClient.get(`/smart-schemes/${schemeId}/logs`, { params })
};

export default smartSchemeApi;
