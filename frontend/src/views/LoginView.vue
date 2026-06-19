<script setup lang="ts">
import { Hide, View } from '@element-plus/icons-vue'
import { Sprout } from '@lucide/vue'
import { ElButton, ElCheckbox, ElIcon, ElInput, ElOption, ElSelect } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createConsumerSession,
  getKnowledgeBasePublicSummary,
  listConsumerUsers,
  login as loginRequest,
  saveAuthTokens,
} from '@/api/client'
import type { ConsumerUserOption, UserRole } from '@/api/types'
import cyberPickleJarLogo from '@/assets/cyber-pickle-jar-logo.png'

type LoginMode = 'admin' | 'user'

interface CharacterPosition {
  faceX: number
  faceY: number
  bodySkew: number
}

const route = useRoute()
const router = useRouter()

const loginMode = ref<LoginMode>('admin')
const username = ref('admin')
const password = ref('AdminPassword123')
const selectedUsername = ref('')
const consumerUsers = ref<ConsumerUserOption[]>([])
const showPassword = ref(false)
const rememberLogin = ref(true)
const loading = ref(false)
const loadingUserOptions = ref(false)
const errorMessage = ref('')
const deploymentDay = ref(1)
const knowledgeBaseCount = ref(0)

const mouseX = ref(0)
const mouseY = ref(0)
const isTyping = ref(false)
const isLookingAtEachOther = ref(false)
const isPurpleBlinking = ref(false)
const isBlackBlinking = ref(false)
const isPurplePeeking = ref(false)

const purpleRef = ref<HTMLElement | null>(null)
const blackRef = ref<HTMLElement | null>(null)
const orangeRef = ref<HTMLElement | null>(null)
const yellowRef = ref<HTMLElement | null>(null)

const userAllowedRedirects = ['/chat', '/knowledge', '/profile']

let purpleBlinkTimer: number | undefined
let blackBlinkTimer: number | undefined
let typingLookTimer: number | undefined
let peekTimer: number | undefined
let peekResetTimer: number | undefined

const purplePosition = computed(() => calculatePosition(purpleRef.value))
const blackPosition = computed(() => calculatePosition(blackRef.value))
const orangePosition = computed(() => calculatePosition(orangeRef.value))
const yellowPosition = computed(() => calculatePosition(yellowRef.value))

const purpleHeight = computed(() =>
  isTyping.value || (password.value.length > 0 && !showPassword.value) ? '440px' : '400px',
)

const purpleTransform = computed(() => {
  if (password.value.length > 0 && showPassword.value) {
    return 'skewX(0deg)'
  }
  if (isTyping.value || (password.value.length > 0 && !showPassword.value)) {
    return `skewX(${purplePosition.value.bodySkew - 12}deg) translateX(40px)`
  }
  return `skewX(${purplePosition.value.bodySkew}deg)`
})

const blackTransform = computed(() => {
  if (password.value.length > 0 && showPassword.value) {
    return 'skewX(0deg)'
  }
  if (isLookingAtEachOther.value) {
    return `skewX(${blackPosition.value.bodySkew * 1.5 + 10}deg) translateX(20px)`
  }
  if (isTyping.value || (password.value.length > 0 && !showPassword.value)) {
    return `skewX(${blackPosition.value.bodySkew * 1.5}deg)`
  }
  return `skewX(${blackPosition.value.bodySkew}deg)`
})

const orangeTransform = computed(() =>
  password.value.length > 0 && showPassword.value
    ? 'skewX(0deg)'
    : `skewX(${orangePosition.value.bodySkew}deg)`,
)

const yellowTransform = computed(() =>
  password.value.length > 0 && showPassword.value
    ? 'skewX(0deg)'
    : `skewX(${yellowPosition.value.bodySkew}deg)`,
)

const purpleEyesStyle = computed(() => ({
  left:
    password.value.length > 0 && showPassword.value
      ? '20px'
      : isLookingAtEachOther.value
        ? '55px'
        : `${45 + purplePosition.value.faceX}px`,
  top:
    password.value.length > 0 && showPassword.value
      ? '35px'
      : isLookingAtEachOther.value
        ? '65px'
        : `${40 + purplePosition.value.faceY}px`,
}))

const blackEyesStyle = computed(() => ({
  left:
    password.value.length > 0 && showPassword.value
      ? '10px'
      : isLookingAtEachOther.value
        ? '32px'
        : `${26 + blackPosition.value.faceX}px`,
  top:
    password.value.length > 0 && showPassword.value
      ? '28px'
      : isLookingAtEachOther.value
        ? '12px'
        : `${32 + blackPosition.value.faceY}px`,
}))

const orangeEyesStyle = computed(() => ({
  left:
    password.value.length > 0 && showPassword.value
      ? '50px'
      : `${82 + orangePosition.value.faceX}px`,
  top:
    password.value.length > 0 && showPassword.value
      ? '85px'
      : `${90 + orangePosition.value.faceY}px`,
}))

const yellowEyesStyle = computed(() => ({
  left:
    password.value.length > 0 && showPassword.value
      ? '20px'
      : `${52 + yellowPosition.value.faceX}px`,
  top:
    password.value.length > 0 && showPassword.value
      ? '35px'
      : `${40 + yellowPosition.value.faceY}px`,
}))

const yellowMouthStyle = computed(() => ({
  left:
    password.value.length > 0 && showPassword.value
      ? '10px'
      : `${40 + yellowPosition.value.faceX}px`,
  top:
    password.value.length > 0 && showPassword.value
      ? '88px'
      : `${88 + yellowPosition.value.faceY}px`,
}))

const purplePupilStyle = computed(() => {
  if (password.value.length > 0 && showPassword.value) {
    return {
      transform: isPurplePeeking.value ? 'translate(4px, 5px)' : 'translate(-4px, -4px)',
    }
  }
  if (isLookingAtEachOther.value) {
    return { transform: 'translate(3px, 4px)' }
  }
  return { transform: `translate(${purplePosition.value.faceX / 3}px, ${purplePosition.value.faceY / 3}px)` }
})

const blackPupilStyle = computed(() => {
  if (password.value.length > 0 && showPassword.value) {
    return { transform: 'translate(-4px, -4px)' }
  }
  if (isLookingAtEachOther.value) {
    return { transform: 'translate(0, -4px)' }
  }
  return { transform: `translate(${blackPosition.value.faceX / 3}px, ${blackPosition.value.faceY / 3}px)` }
})

const simplePupilStyle = computed(() => {
  if (password.value.length > 0 && showPassword.value) {
    return { transform: 'translate(-5px, -4px)' }
  }
  return { transform: 'translate(0, 0)' }
})

onMounted(() => {
  window.addEventListener('mousemove', handleMouseMove)
  scheduleBlink('purple')
  scheduleBlink('black')
  void loadPublicSummary()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', handleMouseMove)
  clearTimer(purpleBlinkTimer)
  clearTimer(blackBlinkTimer)
  clearTimer(typingLookTimer)
  clearPeekTimers()
})

watch(isTyping, (typing) => {
  clearTimer(typingLookTimer)
  if (!typing) {
    isLookingAtEachOther.value = false
    return
  }
  isLookingAtEachOther.value = true
  typingLookTimer = window.setTimeout(() => {
    isLookingAtEachOther.value = false
  }, 800)
})

watch([password, showPassword], () => {
  clearPeekTimers()
  isPurplePeeking.value = false
  if (password.value.length > 0 && showPassword.value) {
    schedulePurplePeek()
  }
})

async function selectLoginMode(mode: LoginMode): Promise<void> {
  loginMode.value = mode
  errorMessage.value = ''
  if (mode === 'admin') {
    username.value = 'admin'
    password.value = 'AdminPassword123'
    return
  }

  password.value = ''
  await loadConsumerUsers()
}

async function submitLogin(): Promise<void> {
  if (loading.value) {
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    if (loginMode.value === 'admin') {
      const response = await loginRequest({
        username: username.value.trim(),
        password: password.value,
      })
      saveAuthTokens(response)
      await router.push(resolvePostLoginPath(response.user.role))
      return
    }

    if (!selectedUsername.value) {
      errorMessage.value = '请选择一个普通用户后进入。'
      return
    }

    const response = await createConsumerSession({ username: selectedUsername.value })
    saveAuthTokens(response)
    await router.push(resolvePostLoginPath(response.user.role))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登录失败，请稍后重试。'
  } finally {
    loading.value = false
  }
}

const clearForm = () => {
  if (loginMode.value === 'admin') {
    username.value = ''
    password.value = ''
  } else {
    selectedUsername.value = ''
  }
  errorMessage.value = ''
}

async function loadConsumerUsers(): Promise<void> {
  if (loadingUserOptions.value) {
    return
  }

  loadingUserOptions.value = true
  errorMessage.value = ''
  try {
    const response = await listConsumerUsers()
    consumerUsers.value = response.items
    selectedUsername.value = response.items[0]?.username ?? ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取用户列表失败，请稍后重试。'
  } finally {
    loadingUserOptions.value = false
  }
}

async function loadPublicSummary(): Promise<void> {
  try {
    const summary = await getKnowledgeBasePublicSummary()
    deploymentDay.value = Math.max(summary.deployment_day, 1)
    knowledgeBaseCount.value = Math.max(summary.active_count, 0)
  } catch {
    deploymentDay.value = 1
    knowledgeBaseCount.value = 0
  }
}

function resolvePostLoginPath(role: UserRole): string {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  if (role === 'admin') {
    return redirect && redirect !== '/login' ? redirect : '/knowledge-bases'
  }
  if (userAllowedRedirects.some((path) => redirect === path || redirect.startsWith(`${path}?`))) {
    return redirect
  }
  return '/chat'
}

function handleMouseMove(event: MouseEvent): void {
  mouseX.value = event.clientX
  mouseY.value = event.clientY
}

function calculatePosition(element: HTMLElement | null): CharacterPosition {
  if (!element) {
    return { faceX: 0, faceY: 0, bodySkew: 0 }
  }

  const rect = element.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 3
  const deltaX = mouseX.value - centerX
  const deltaY = mouseY.value - centerY

  return {
    faceX: clamp(deltaX / 20, -15, 15),
    faceY: clamp(deltaY / 30, -10, 10),
    bodySkew: clamp(-deltaX / 120, -6, 6),
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function scheduleBlink(character: 'purple' | 'black'): void {
  const timeout = window.setTimeout(
    () => {
      if (character === 'purple') {
        isPurpleBlinking.value = true
        purpleBlinkTimer = window.setTimeout(() => {
          isPurpleBlinking.value = false
          scheduleBlink(character)
        }, 150)
      } else {
        isBlackBlinking.value = true
        blackBlinkTimer = window.setTimeout(() => {
          isBlackBlinking.value = false
          scheduleBlink(character)
        }, 150)
      }
    },
    Math.random() * 4000 + 3000,
  )

  if (character === 'purple') {
    purpleBlinkTimer = timeout
  } else {
    blackBlinkTimer = timeout
  }
}

function schedulePurplePeek(): void {
  peekTimer = window.setTimeout(
    () => {
      isPurplePeeking.value = true
      peekResetTimer = window.setTimeout(() => {
        isPurplePeeking.value = false
        if (password.value.length > 0 && showPassword.value) {
          schedulePurplePeek()
        }
      }, 800)
    },
    Math.random() * 3000 + 2000,
  )
}

function clearTimer(timer: number | undefined): void {
  if (timer !== undefined) {
    window.clearTimeout(timer)
  }
}

function clearPeekTimers(): void {
  clearTimer(peekTimer)
  clearTimer(peekResetTimer)
}
</script>

<template>
  <main class="login-page">
    <section class="login-visual" aria-hidden="true">
      <div class="visual-brand">
        <img class="brand-logo" :src="cyberPickleJarLogo" alt="" />
        <span>赛博腌菜缸</span>
      </div>

      <div class="character-stage">
        <div
          ref="purpleRef"
          class="character purple-character"
          :style="{ height: purpleHeight, transform: purpleTransform }"
        >
          <div class="eyes purple-eyes" :style="purpleEyesStyle">
            <span class="eye-ball small" :class="{ blinking: isPurpleBlinking }">
              <span v-if="!isPurpleBlinking" class="iris" :style="purplePupilStyle" />
            </span>
            <span class="eye-ball small" :class="{ blinking: isPurpleBlinking }">
              <span v-if="!isPurpleBlinking" class="iris" :style="purplePupilStyle" />
            </span>
          </div>
        </div>

        <div
          ref="blackRef"
          class="character black-character"
          :style="{ transform: blackTransform }"
        >
          <div class="eyes black-eyes" :style="blackEyesStyle">
            <span class="eye-ball tiny" :class="{ blinking: isBlackBlinking }">
              <span v-if="!isBlackBlinking" class="iris" :style="blackPupilStyle" />
            </span>
            <span class="eye-ball tiny" :class="{ blinking: isBlackBlinking }">
              <span v-if="!isBlackBlinking" class="iris" :style="blackPupilStyle" />
            </span>
          </div>
        </div>

        <div
          ref="orangeRef"
          class="character orange-character"
          :style="{ transform: orangeTransform }"
        >
          <div class="eyes dot-eyes orange-eyes" :style="orangeEyesStyle">
            <span class="dot-pupil" :style="simplePupilStyle" />
            <span class="dot-pupil" :style="simplePupilStyle" />
          </div>
        </div>

        <div
          ref="yellowRef"
          class="character yellow-character"
          :style="{ transform: yellowTransform }"
        >
          <div class="eyes dot-eyes yellow-eyes" :style="yellowEyesStyle">
            <span class="dot-pupil" :style="simplePupilStyle" />
            <span class="dot-pupil" :style="simplePupilStyle" />
          </div>
          <span class="yellow-mouth" :style="yellowMouthStyle" />
        </div>
      </div>

      <div class="visual-footer">
        <span>私有部署</span>
        <span>引用溯源</span>
        <span>团队知识问答</span>
      </div>
    </section>

    <section class="login-panel" aria-labelledby="login-title">
      <div class="mobile-brand">
        <img class="brand-logo" :src="cyberPickleJarLogo" alt="" />
        <span>赛博腌菜缸</span>
      </div>

      <div class="login-shell">
        <header class="login-header">
          <p class="pickle-tagline">
            <img class="tagline-icon" :src="cyberPickleJarLogo" alt="" />
            <span>腌菜第 {{ deploymentDay }} 天，缸体无裂，知识未发酵</span>
          </p>
          <span class="pickle-count">共{{ knowledgeBaseCount }}缸菜</span>
          <h1 id="login-title">
            <Sprout class="title-icon" aria-hidden="true" />
            <span class="title-copy">
              <span>今日宜：取菜</span>
              <span>（但请先确认没过期）</span>
            </span>
          </h1>
        </header>

        <div class="mode-switch" role="group" aria-label="选择登录角色">
          <button
            class="mode-button"
            :class="{ active: loginMode === 'admin' }"
            type="button"
            @click="selectLoginMode('admin')"
          >
            管理员登录
          </button>
          <button
            class="mode-button"
            :class="{ active: loginMode === 'user' }"
            type="button"
            @click="selectLoginMode('user')"
          >
            用户登录
          </button>
        </div>

        <form class="form-stack" @submit.prevent="submitLogin">
          <template v-if="loginMode === 'admin'">
            <label class="field-label">
              用户名
              <el-input
                v-model="username"
                placeholder="请输入管理员用户名"
                size="large"
                autocomplete="username"
                @focus="isTyping = true"
                @blur="isTyping = false"
              />
            </label>

            <label class="field-label">
              密码
              <el-input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                size="large"
                autocomplete="current-password"
                @focus="isTyping = true"
                @blur="isTyping = false"
              >
                <template #suffix>
                  <el-icon
                    class="password-toggle"
                    role="button"
                    tabindex="0"
                    :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                    @click="showPassword = !showPassword"
                    @keydown.enter.prevent="showPassword = !showPassword"
                  >
                    <component :is="showPassword ? Hide : View" />
                  </el-icon>
                </template>
              </el-input>
            </label>

            <div class="login-options">
              <el-checkbox v-model="rememberLogin">记住登录状态</el-checkbox>
              <button class="ka-link-button" type="button" @click="clearForm">清空</button>
            </div>
          </template>

          <template v-else>
            <label class="field-label">
              选择用户
              <el-select
                v-model="selectedUsername"
                filterable
                :loading="loadingUserOptions"
                :disabled="loadingUserOptions || consumerUsers.length === 0"
                placeholder="请选择普通用户"
                size="large"
                @focus="isTyping = true"
                @blur="isTyping = false"
              >
                <el-option
                  v-for="userOption in consumerUsers"
                  :key="userOption.username"
                  :label="`${userOption.display_name}（${userOption.username}）`"
                  :value="userOption.username"
                />
              </el-select>
            </label>

            <div class="login-options">
              <span class="user-entry-note">用户入口无需密码</span>
              <button class="ka-link-button" type="button" @click="loadConsumerUsers">刷新列表</button>
            </div>
          </template>

          <p v-if="errorMessage" class="login-error">{{ errorMessage }}</p>

          <el-button
            type="primary"
            size="large"
            native-type="submit"
            :loading="loading"
            class="login-button"
          >
            {{ loginMode === 'admin' ? '登录管理后台' : '进入用户页面' }}
          </el-button>
        </form>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(500px, 1fr) minmax(420px, 0.82fr);
  min-height: 100vh;
  background: #fbfcfb;
}

.login-visual {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 100vh;
  overflow: hidden;
  padding: 44px 52px 36px;
  color: #f8fffb;
  background:
    linear-gradient(90deg, rgb(255 255 255 / 7%) 1px, transparent 1px),
    linear-gradient(180deg, rgb(255 255 255 / 7%) 1px, transparent 1px),
    linear-gradient(145deg, #09584f 0%, #0f766e 48%, #3c6b46 100%);
  background-size:
    28px 28px,
    28px 28px,
    auto;
}

.login-visual::after {
  position: absolute;
  inset: auto 0 0;
  height: 34%;
  background: linear-gradient(180deg, transparent, rgb(4 25 23 / 28%));
  content: '';
  pointer-events: none;
}

.visual-brand,
.mobile-brand {
  position: relative;
  z-index: 2;
  display: inline-flex;
  gap: 14px;
  align-items: center;
  color: #f8fffb;
  font-size: 28px;
  font-weight: 800;
}

.brand-logo {
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  border: 1px solid rgb(255 255 255 / 28%);
  border-radius: 9px;
  background: rgb(255 255 255 / 14%);
  box-shadow:
    0 12px 28px rgb(5 32 29 / 16%),
    inset 0 1px 0 rgb(255 255 255 / 22%);
  object-fit: cover;
}

.character-stage {
  position: relative;
  z-index: 1;
  align-self: end;
  justify-self: center;
  width: 550px;
  max-width: 100%;
  height: 470px;
  transform: translateY(20px);
}

.character {
  position: absolute;
  bottom: 0;
  transform-origin: bottom center;
  transition:
    height 700ms ease,
    transform 700ms ease;
}

.purple-character {
  left: 70px;
  z-index: 1;
  width: 180px;
  border-radius: 10px 10px 0 0;
  background: #6c3ff5;
  box-shadow: inset 18px 0 0 rgb(255 255 255 / 6%);
}

.black-character {
  left: 240px;
  z-index: 2;
  width: 120px;
  height: 310px;
  border-radius: 8px 8px 0 0;
  background: #2d2d2d;
  box-shadow: inset -14px 0 0 rgb(255 255 255 / 5%);
}

.orange-character {
  left: 0;
  z-index: 3;
  width: 240px;
  height: 200px;
  border-radius: 120px 120px 0 0;
  background: #ff9b6b;
  box-shadow: inset -18px 0 0 rgb(126 54 31 / 9%);
}

.yellow-character {
  left: 310px;
  z-index: 4;
  width: 140px;
  height: 230px;
  border-radius: 70px 70px 0 0;
  background: #e8d754;
  box-shadow: inset -14px 0 0 rgb(89 78 16 / 9%);
}

.eyes {
  position: absolute;
  display: flex;
  transition:
    left 700ms ease,
    top 700ms ease;
}

.purple-eyes {
  gap: 32px;
}

.black-eyes {
  gap: 24px;
}

.dot-eyes {
  gap: 28px;
  transition:
    left 200ms ease,
    top 200ms ease;
}

.yellow-eyes {
  gap: 24px;
}

.eye-ball {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 999px;
  background: #fff;
  transition: height 150ms ease;
}

.eye-ball.small {
  width: 18px;
  height: 18px;
}

.eye-ball.tiny {
  width: 16px;
  height: 16px;
}

.eye-ball.blinking {
  height: 2px;
}

.iris {
  display: block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #2d2d2d;
  transition: transform 100ms ease-out;
}

.black-eyes .iris {
  width: 6px;
  height: 6px;
}

.dot-pupil {
  display: block;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #2d2d2d;
  transition: transform 100ms ease-out;
}

.yellow-mouth {
  position: absolute;
  width: 80px;
  height: 4px;
  border-radius: 999px;
  background: #2d2d2d;
  transition:
    left 200ms ease,
    top 200ms ease;
}

.visual-footer {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  align-items: center;
  color: rgb(248 255 251 / 70%);
  font-size: 13px;
}

.visual-footer span {
  padding-left: 14px;
  border-left: 2px solid rgb(248 255 251 / 32%);
}

.login-panel {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 40px;
  background:
    linear-gradient(90deg, rgb(15 118 110 / 5%) 0 1px, transparent 1px 100%),
    #fbfcfb;
  background-size: 34px 100%;
}

.mobile-brand {
  display: none;
  margin-bottom: 34px;
  color: var(--ka-primary-deep);
}

.mobile-brand .brand-logo {
  border-color: rgb(15 118 110 / 18%);
  background: var(--ka-primary-soft);
  box-shadow: 0 10px 24px rgb(15 118 110 / 13%);
}

.login-shell {
  width: min(100%, 440px);
}

.login-header {
  margin-bottom: 28px;
  text-align: center;
}

.login-header p {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--ka-primary);
  font-size: 23px;
  font-weight: 750;
  line-height: 32px;
}

.tagline-icon {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  border-radius: 7px;
  object-fit: cover;
}

.pickle-count {
  display: block;
  margin-bottom: 18px;
  color: var(--ka-text-secondary);
  font-size: 22px;
  font-weight: 700;
  line-height: 30px;
}

.login-header h1 {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  gap: 10px;
  width: max-content;
  max-width: min(560px, calc(100vw - 48px));
  margin: 0;
  margin-inline: auto;
  color: var(--ka-text);
  font-size: 40px;
  font-weight: 800;
  line-height: 50px;
  letter-spacing: 0;
}

.title-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 auto;
  margin-top: 5px;
  color: var(--ka-primary);
  stroke-width: 2.4;
}

.title-copy {
  display: grid;
  justify-items: center;
  min-width: 0;
}

.title-copy span {
  display: block;
  white-space: nowrap;
}

.mode-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  padding: 5px;
  border: 1px solid var(--ka-border);
  border-radius: 8px;
  margin-bottom: 24px;
  background: #eef4f1;
}

.mode-button {
  min-height: 44px;
  border: 0;
  border-radius: 6px;
  color: var(--ka-text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  font-weight: 800;
  transition:
    color 160ms ease,
    background 160ms ease,
    box-shadow 160ms ease;
}

.mode-button:hover {
  color: var(--ka-primary-deep);
}

.mode-button.active {
  color: #fff;
  background: var(--ka-primary);
  box-shadow: 0 10px 20px rgb(15 118 110 / 18%);
}

.form-stack {
  display: grid;
  gap: 18px;
}

.field-label {
  display: grid;
  gap: 8px;
  color: var(--ka-text);
  font-size: 14px;
  font-weight: 800;
}

.form-stack :deep(.el-input__wrapper),
.form-stack :deep(.el-select__wrapper) {
  min-height: 48px;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 0 0 1px var(--ka-border) inset;
}

.form-stack :deep(.el-input__wrapper.is-focus),
.form-stack :deep(.el-select__wrapper.is-focused) {
  box-shadow:
    0 0 0 1px var(--ka-primary) inset,
    0 0 0 3px rgb(15 118 110 / 12%);
}

.password-toggle {
  cursor: pointer;
  outline: none;
}

.password-toggle:focus-visible {
  color: var(--ka-primary);
}

.login-options {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
}

.user-entry-note {
  color: var(--ka-text-secondary);
  font-size: 13px;
}

.login-button {
  width: 100%;
  min-height: 48px;
  margin-top: 4px;
}

.login-error {
  padding: 12px 14px;
  border: 1px solid #f4c8c1;
  border-radius: 6px;
  margin: 0;
  color: var(--ka-error);
  background: #fff0ed;
  font-size: 13px;
  line-height: 20px;
}

@media (max-width: 980px) {
  .login-page {
    grid-template-columns: 1fr;
  }

  .login-visual {
    display: none;
  }

  .login-panel {
    align-content: center;
    padding: 28px;
  }

  .mobile-brand {
    display: inline-flex;
    justify-self: center;
  }
}

@media (max-width: 560px) {
  .login-panel {
    padding: 22px;
  }

  .login-header h1 {
    max-width: calc(100vw - 44px);
    margin-inline: auto;
    font-size: 30px;
    line-height: 38px;
  }

  .login-header p {
    max-width: 320px;
    margin-inline: auto;
  }

  .tagline-icon {
    width: 28px;
    height: 28px;
  }

  .title-icon {
    width: 32px;
    height: 32px;
    margin-top: 3px;
  }

  .mode-switch {
    grid-template-columns: 1fr;
  }
}
</style>
