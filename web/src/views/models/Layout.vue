<template>
  <div class="models-layout">
    <div class="layout-header">
      <h2>模型管理</h2>
    </div>
    <router-view />
  </div>
</template>

<style scoped>
.models-layout {
  padding: 20px;
}

.layout-header {
  margin-bottom: 16px;
}

.layout-header h2 {
  margin-bottom: 0;
}
</style>
