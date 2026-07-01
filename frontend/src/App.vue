<script setup lang="ts">
import { ElConfigProvider } from 'element-plus'
</script>

<template>
  <el-config-provider>
    <router-view v-slot="{ Component }">
      <keep-alive include="ChatView">
        <component :is="Component" />
      </keep-alive>
    </router-view>
  </el-config-provider>
</template>
