<script setup lang="ts">
import { Lock } from '@element-plus/icons-vue'
import { ElButton, ElIcon } from 'element-plus'

import AppLayout from '@/components/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <section class="state-page">
      <el-icon class="state-icon">
        <Lock />
      </el-icon>
      <h1>无权访问</h1>
      <p>当前账号没有访问该页面的权限。如需使用此功能，请联系管理员。</p>
      <div>
        <RouterLink to="/chat">
          <el-button type="primary"> 返回对话问答 </el-button>
        </RouterLink>
        <RouterLink to="/knowledge-bases">
          <el-button>返回知识库</el-button>
        </RouterLink>
      </div>
    </section>
  </AppLayout>
</template>

<style scoped>
.state-page {
  display: grid;
  min-height: calc(100vh - var(--ka-header-height));
  place-content: center;
  justify-items: center;
  gap: 16px;
  padding: 32px;
  text-align: center;
}

.state-icon {
  display: grid;
  width: 68px;
  height: 68px;
  place-items: center;
  border-radius: 16px;
  color: var(--ka-primary);
  background: var(--ka-surface-container);
  font-size: 34px;
}

h1 {
  margin: 0;
}

p {
  max-width: 420px;
  margin: 0;
  color: var(--ka-text-secondary);
  line-height: 1.7;
}

div {
  display: flex;
  gap: 10px;
}
</style>
