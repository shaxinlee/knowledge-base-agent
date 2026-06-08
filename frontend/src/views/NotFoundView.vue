<script setup lang="ts">
import { ElButton } from 'element-plus'

import AppLayout from '@/components/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <section class="state-page">
      <strong>404</strong>
      <h1>页面不存在</h1>
      <p>你访问的页面可能已被删除，或链接地址不正确。</p>
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

.state-page > strong {
  color: var(--ka-primary);
  font-size: 72px;
  line-height: 1;
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
