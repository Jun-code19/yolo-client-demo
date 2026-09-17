import axios from 'axios';

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: '/api/v2',
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

// 数据推送相关 API
export const dataPushApi = {
    // 获取推送配置列表（分页）
    getPushConfigs(params = {}) {
      const token = localStorage.getItem('token');
      return axios.get('/api/v1/data_push/list', {
        params,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      });
    },
    
    // 创建推送配置
    createPushConfig(configData) {
      return apiClient.post('/data_push/create', configData);
    },
    
    // 更新推送配置
    updatePushConfig(pushId, configData) {
      return apiClient.put(`/data_push/${pushId}`, configData);
    },
    
    // 删除推送配置
    deletePushConfig(pushId) {
      return apiClient.delete(`/data_push/${pushId}`);
    },
    
    // 测试推送配置
    testPushConfig(pushId) {
      return apiClient.post(`/data_push/test/${pushId}`);
    },
    
    // 获取推送统计信息（检测服务内存计数）
    getPushStats() {
      return apiClient.get('/data_push/stats');
    },

    // 获取推送执行记录
    getPushLogs(params = {}) {
      return axios.get('/api/v1/data_push/logs', {
        params,
        headers: {
          'Content-Type': 'application/json',
          Authorization: localStorage.getItem('token') ? `Bearer ${localStorage.getItem('token')}` : ''
        }
      });
    },

    // 获取推送概览统计
    getPushOverview() {
      return apiClient.get('/data_push/overview');
    },
    
    // 重新加载推送配置
    reloadPushConfig(pushId) {
      return apiClient.post(`/data_push/reload/${pushId}`);
    }
  }; 