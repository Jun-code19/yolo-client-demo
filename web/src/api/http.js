import axios from 'axios'
import { ElMessage } from 'element-plus'

/**
 * 管理 API（/api/v1）通用 axios：Bearer token + 401 跳转登录
 */
export function attachAuthInterceptors(client, { skipAuthUrls = [] } = {}) {
  client.interceptors.request.use(
    (config) => {
      const url = config.url || ''
      if (skipAuthUrls.some((u) => url === u || url.startsWith(`${u}?`))) {
        return config
      }
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    },
    (error) => Promise.reject(error)
  )

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('userInfo')
        ElMessage.error('登录已过期，请重新登录')
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }
  )

  return client
}

export function createV1Client(options = {}) {
  const { timeout = 10000, skipAuthUrls = ['/token'], ...rest } = options
  const client = axios.create({
    baseURL: '/api/v1',
    timeout,
    headers: { 'Content-Type': 'application/json' },
    ...rest,
  })
  attachAuthInterceptors(client, { skipAuthUrls })
  return client
}

/** 默认 /api/v1 客户端（多数模块可直接 import） */
export const apiV1 = createV1Client()
