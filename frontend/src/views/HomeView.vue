<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
import { ElIcon, ElTag } from 'element-plus'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>

<template>
  <main class="home-shell">
    <section class="status-panel">
      <el-icon class="status-icon" :size="28">
        <Connection />
      </el-icon>
      <div>
        <h1>{{ appStore.serviceName }}</h1>
        <p>Phase 0 foundation is ready.</p>
      </div>
      <el-tag type="success" effect="plain"> v{{ appStore.version }} </el-tag>
    </section>
  </main>
</template>

<style scoped>
.home-shell {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px;
}

.status-panel {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  width: min(100%, 680px);
  padding: 24px;
  border: 1px solid #d7dde7;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 14px 36px rgb(23 32 42 / 8%);
}

.status-icon {
  color: #2870bd;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 650;
  letter-spacing: 0;
}

p {
  margin: 6px 0 0;
  color: #5d6d7e;
  font-size: 14px;
}

@media (max-width: 560px) {
  .status-panel {
    grid-template-columns: auto minmax(0, 1fr);
  }
}
</style>
