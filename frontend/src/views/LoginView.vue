<script setup lang="ts">
import { Hide, View } from '@element-plus/icons-vue'
import { ElButton, ElCheckbox, ElIcon, ElInput } from 'element-plus'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { login as loginRequest, saveAuthTokens } from '@/api/client'

const username = ref('admin')
const password = ref('AdminPassword123')
const showPassword = ref(false)
const loading = ref(false)
const errorMessage = ref('')
const router = useRouter()

const login = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await loginRequest({ username: username.value, password: password.value })
    saveAuthTokens(response)
    await router.push('/chat')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

const clearForm = () => {
  username.value = ''
  password.value = ''
  errorMessage.value = ''
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">
        <div class="brand-mark">KB</div>
        <div>
          <h1>知识库 Agent 助手</h1>
          <p>面向团队资料的智能问答工作台</p>
        </div>
      </div>

      <div class="form-stack">
        <label>
          用户名
          <el-input v-model="username" placeholder="请输入用户名" size="large" />
        </label>
        <label>
          密码
          <el-input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="请输入密码"
            size="large"
            @keyup.enter="login"
          >
            <template #suffix>
              <el-icon class="password-toggle" @click="showPassword = !showPassword">
                <component :is="showPassword ? Hide : View" />
              </el-icon>
            </template>
          </el-input>
        </label>
      </div>

      <div class="login-options">
        <el-checkbox>记住登录状态</el-checkbox>
        <button class="ka-link-button" type="button" @click="clearForm">清空</button>
      </div>

      <el-button type="primary" size="large" :loading="loading" class="login-button" @click="login">
        登录
      </el-button>

      <p v-if="errorMessage" class="login-error">{{ errorMessage }}</p>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px;
  background:
    linear-gradient(180deg, rgb(250 248 255 / 90%), rgb(242 243 245 / 100%)), var(--ka-background);
}

.login-card {
  width: min(100%, 420px);
  padding: 32px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 16px 48px rgb(29 33 41 / 6%);
}

.login-brand {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  border-radius: 8px;
  color: #fff;
  background: var(--ka-primary);
  font-weight: 800;
}

h1 {
  margin: 0;
  font-size: 22px;
  line-height: 30px;
}

p {
  margin: 4px 0 0;
  color: var(--ka-text-secondary);
}

.form-stack {
  display: grid;
  gap: 18px;
}

label {
  display: grid;
  gap: 8px;
  color: var(--ka-text);
  font-size: 14px;
  font-weight: 700;
}

.password-toggle {
  cursor: pointer;
}

.login-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 24px;
}

.login-button {
  width: 100%;
}

.login-error {
  padding: 12px;
  border-radius: 4px;
  margin-top: 18px;
  color: var(--ka-error);
  background: #fff0ed;
  font-size: 13px;
}
</style>
