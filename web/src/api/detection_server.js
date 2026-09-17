import axios from 'axios';

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: '/api/v2/detection',
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

export const startDetection = async (configId) => {
    try {
        const response = await apiClient.post(`${configId}/start`);
        return response.data;
    } catch (error) {
        // console.error('启动检测任务失败:', error);
        throw error;
    }
};

export const stopDetection = async (configId) => {
    try {
        const response = await apiClient.post(`${configId}/stop`);
        return response.data;
    } catch (error) {
        // console.error('停止检测任务失败:', error);
        throw error;
    }
};

export const getDetectionStatus = async () => {
    try {
        const response = await apiClient.get(`/status`);
        return response.data;
    } catch (error) {
        // console.error('获取检测任务状态失败:', error);
        throw error;
    }
};