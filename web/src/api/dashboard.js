import axios from 'axios'

const API_BASE_URL_v1 = '/api/v1'
const API_BASE_URL_v2 = '/api/v2'

const apiClient_v1 = axios.create({
  baseURL: API_BASE_URL_v1,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

const apiClient_v2 = axios.create({
  baseURL: API_BASE_URL_v2,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 添加请求拦截器，自动添加认证token
apiClient_v1.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)
// 添加请求拦截器，自动添加认证token
apiClient_v2.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

export const DEFAULT_DASHBOARD_SCREEN_NAME = '边缘AI展示大屏'

export const dashboardIntegrationApi = {
  getConfig: () => apiClient_v1.get('/settings/dashboard-integrations'),
  saveConfig: (data) => apiClient_v1.put('/settings/dashboard-integrations', data),
  testWaitTime: (data) => apiClient_v1.post('/settings/dashboard-integrations/test-wait-time', data),
}

export const getWaitTimeData = async (timeoutMs = 70000) => {
  try {
    const response = await apiClient_v1.get('/dashboard/wait-time', { timeout: timeoutMs });
    return response.data?.data ?? response.data;
  } catch (error) {
    console.error('Error fetching wait time data:', error);
    throw error;
  }
};

export const getWeatherData = async (lat, lon) => {
  try {
    const response = await apiClient_v1.get('/dashboard/weather', {
      params: { lat, lon },
    });
    return response.data?.data ?? response.data;
  } catch (error) {
    console.error('Error fetching weather data:', error);
    throw error;
  }
};

// 导出API和客户端
export { apiClient_v1,apiClient_v2 }