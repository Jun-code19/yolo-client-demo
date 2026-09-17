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
    // 对于token端点的请求，不修改Content-Type
    if (config.url === '/token') {
      return config;
    }
    
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
    // 处理401错误（未授权，token过期）
    if (error.response && error.response.status === 401) {
      // 清除token和用户信息
      localStorage.removeItem('token');
      localStorage.removeItem('userInfo');
      
      // 显示提示信息
      ElMessage.error('登录已过期，请重新登录');
      
      // 重定向到登录页面
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default {
    // 系统日志相关API
  getSyslogs(params) {
    return apiClient.get('/syslogs/', { params });
  },
  
  exportSystemLogs(params) {
    return apiClient.get('/system/logs/export', { params });
  },
  
  clearSystemLogs(days) {
    return apiClient.delete(`/system/logs/clear?days=${days}`);
  },
  // 添加获取检测日志的API函数
  getDetectionLogs(params = { skip: 0, limit: 100 }) {
    return apiClient.get('/detection/logs/', { params });
  },
  
  // 导出检测日志
  exportDetectionLogs(params) {
    return apiClient.get('/detection/logs/export', {
      params,
      responseType: 'blob' // 使用blob响应类型来处理文件下载
    });
  },
  
  // 清除检测日志
  clearDetectionLogs(days) {
    return apiClient.delete(`/detection/logs/clear?days=${days}`);
  },

  // 获取系统状态
  getSystemStatus() {
    return apiClient.get('/system/status');
  },
  
}