import { apiV1 as apiClient } from './http';

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