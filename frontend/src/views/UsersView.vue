<script setup lang="ts">
import { Delete, Edit, Key, Plus, Search } from '@element-plus/icons-vue'
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
} from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createUser,
  deleteUser,
  disableUser,
  enableUser,
  getAccessToken,
  listUsers,
  resetUserPassword,
  updateUser,
} from '@/api/client'
import type { User, UserRole } from '@/api/types'
import AppLayout from '@/components/AppLayout.vue'
import PageHeader from '@/components/PageHeader.vue'

const router = useRouter()
const users = ref<User[]>([])
const keyword = ref('')
const roleFilter = ref<'all' | UserRole>('all')
const activeFilter = ref<'all' | 'active' | 'disabled'>('all')
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref('')
const dialogVisible = ref(false)
const editingUser = ref<User | null>(null)
const form = reactive({
  email: '',
  username: '',
  display_name: '',
  password: '',
  role: 'user' as UserRole,
})

onMounted(async () => {
  if (!getAccessToken()) {
    await router.push('/login')
    return
  }
  await loadUsers()
})

async function loadUsers(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await listUsers({
      page: 1,
      page_size: 50,
      keyword: keyword.value.trim() || undefined,
      role: roleFilter.value === 'all' ? undefined : roleFilter.value,
      is_active:
        activeFilter.value === 'all' ? undefined : activeFilter.value === 'active',
    })
    users.value = response.items
  } catch (error) {
    handleError(error)
  } finally {
    loading.value = false
  }
}

function openCreateDialog(): void {
  editingUser.value = null
  form.email = ''
  form.username = ''
  form.display_name = ''
  form.password = ''
  form.role = 'user'
  dialogVisible.value = true
}

function openEditDialog(user: User): void {
  editingUser.value = user
  form.email = ''
  form.username = user.username
  form.display_name = user.display_name
  form.password = ''
  form.role = user.role
  dialogVisible.value = true
}

async function saveUser(): Promise<void> {
  const displayName = form.display_name.trim()
  if (!displayName) {
    errorMessage.value = '显示名不能为空。'
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    if (editingUser.value) {
      await updateUser(editingUser.value.id, {
        display_name: displayName,
        role: form.role,
      })
      ElMessage.success('用户已更新')
    } else {
      if (!form.email.trim() || !form.username.trim() || form.password.length < 8) {
        errorMessage.value = '请填写邮箱、用户名和至少 8 位密码。'
        return
      }
      await createUser({
        email: form.email.trim(),
        username: form.username.trim(),
        display_name: displayName,
        password: form.password,
        role: form.role,
      })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await loadUsers()
  } catch (error) {
    handleError(error)
  } finally {
    saving.value = false
  }
}

async function toggleUserStatus(user: User): Promise<void> {
  try {
    if (user.is_active) {
      await disableUser(user.id)
      ElMessage.success('用户已禁用')
    } else {
      await enableUser(user.id)
      ElMessage.success('用户已启用')
    }
    await loadUsers()
  } catch (error) {
    handleError(error)
  }
}

async function resetPassword(user: User): Promise<void> {
  try {
    const result = await ElMessageBox.prompt(`为 ${user.username} 设置新密码`, '重置密码', {
      confirmButtonText: '重置',
      cancelButtonText: '取消',
      inputType: 'password',
      inputPattern: /^.{8,}$/,
      inputErrorMessage: '密码至少 8 位。',
    })
    await resetUserPassword(user.id, { new_password: result.value })
    ElMessage.success('密码已重置')
  } catch (error) {
    if (error !== 'cancel') {
      handleError(error)
    }
  }
}

async function deleteUserConfirm(user: User): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户 "${user.display_name}"（${user.username}）吗？此操作不可撤销。`,
      '删除用户',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await deleteUser(user.id)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel') {
      handleError(error)
    }
  }
}

function resetFilters(): void {
  keyword.value = ''
  roleFilter.value = 'all'
  activeFilter.value = 'all'
  void loadUsers()
}

function formatTime(value: string | null): string {
  if (!value) {
    return '-'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function handleError(error: unknown): void {
  errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试。'
}
</script>

<template>
  <AppLayout>
    <section class="content-page">
      <PageHeader title="用户管理" subtitle="管理内部成员账号、角色和登录状态。">
        <template #actions>
          <el-button type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon>
            新建用户
          </el-button>
        </template>
      </PageHeader>

      <div class="ka-toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索用户名或显示名..."
          class="toolbar-search"
          size="large"
          @keyup.enter="loadUsers"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="roleFilter" size="large" class="small-select">
          <el-option label="全部角色" value="all" />
          <el-option label="admin" value="admin" />
          <el-option label="user" value="user" />
        </el-select>
        <el-select v-model="activeFilter" size="large" class="small-select">
          <el-option label="全部状态" value="all" />
          <el-option label="启用" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" :loading="loading" @click="loadUsers">查询</el-button>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

      <section class="table-card ka-card">
        <table class="ka-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>显示名</th>
              <th>角色</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="users.length === 0">
              <td colspan="7" class="empty-cell">
                {{ loading ? '正在加载用户...' : '当前筛选条件下没有用户' }}
              </td>
            </tr>
            <tr v-for="user in users" :key="user.id">
              <td>
                <strong>{{ user.username }}</strong>
              </td>
              <td>{{ user.display_name }}</td>
              <td>
                <span :class="['ka-status', user.role === 'admin' ? 'processing' : 'muted']">{{
                  user.role
                }}</span>
              </td>
              <td>
                <span :class="['ka-status', user.is_active ? 'success' : 'danger']">
                  {{ user.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td>{{ formatTime(user.created_at) }}</td>
              <td>{{ formatTime(user.last_login_at) }}</td>
              <td>
                <div class="ka-actions">
                  <button class="ka-link-button" @click="openEditDialog(user)">
                    <el-icon><Edit /></el-icon>
                    编辑
                  </button>
                  <button
                    :class="['ka-link-button', user.is_active ? 'ka-danger-link' : '']"
                    @click="toggleUserStatus(user)"
                  >
                    {{ user.is_active ? '禁用' : '启用' }}
                  </button>
                  <button class="ka-link-button" @click="resetPassword(user)">
                    <el-icon><Key /></el-icon>
                    重置密码
                  </button>
                  <button class="ka-link-button ka-danger-link" @click="deleteUserConfirm(user)">
                    <el-icon><Delete /></el-icon>
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <el-dialog
        v-model="dialogVisible"
        :title="editingUser ? '编辑用户' : '新建用户'"
        width="520px"
      >
        <el-form label-position="top">
          <el-form-item v-if="!editingUser" label="邮箱">
            <el-input v-model="form.email" />
          </el-form-item>
          <el-form-item v-if="!editingUser" label="用户名">
            <el-input v-model="form.username" />
          </el-form-item>
          <el-form-item label="显示名">
            <el-input v-model="form.display_name" />
          </el-form-item>
          <el-form-item v-if="!editingUser" label="初始密码">
            <el-input v-model="form.password" type="password" show-password />
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="form.role" class="form-select">
              <el-option label="user" value="user" />
              <el-option label="admin" value="admin" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveUser">保存</el-button>
        </template>
      </el-dialog>
    </section>
  </AppLayout>
</template>

<style scoped>
.content-page {
  padding: 24px;
}

.toolbar-search {
  flex: 1 1 340px;
}

.small-select {
  width: 150px;
}

.table-card {
  overflow: auto;
  margin-top: 18px;
}

.error-message {
  margin: 16px 0 0;
  color: #b42318;
}

.empty-cell {
  padding: 36px;
  color: var(--ka-text-secondary);
  text-align: center;
}

.form-select {
  width: 100%;
}
</style>
