<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import SvgIcon from '@/components/SvgIcon.vue'
import { ROLE_LABEL } from '@/utils/permission'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const NAV = [
  { name: 'check', path: '/check', label: '风险检查', icon: 'search' },
  { name: 'workbench', path: '/workbench', label: '对话工作台', icon: 'chat' },
  { name: 'dashboard', path: '/dashboard', label: '风险看板', icon: 'chart' },
  { name: 'rules', path: '/rules', label: '规则管理', icon: 'rules' },
  { name: 'cases', path: '/cases', label: '案件审核', icon: 'cases' },
  { name: 'blacklist', path: '/blacklist', label: '黑名单', icon: 'ban' },
  { name: 'profile', path: '/profile', label: '用户画像', icon: 'user' }
]

const active = computed(() => route.name)
const roleLabel = computed(() => ROLE_LABEL[auth.operator?.role || ''] || '未授权角色')

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout">
    <aside class="rail">
      <div class="brand">
        <div class="brand-mark"><SvgIcon name="shield" :size="18" /></div>
        <div class="brand-text">
          <strong>风控智能助手</strong>
          <span>Risk Agent</span>
        </div>
      </div>

      <nav class="nav">
        <router-link
          v-for="item in NAV"
          :key="item.name"
          :to="item.path"
          class="nav-item"
          :class="{ on: active === item.name }"
        >
          <SvgIcon :name="item.icon" :size="17" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="rail-foot">
        <div class="who">
          <div class="avatar">{{ (auth.operator?.username || 'U').slice(0, 1).toUpperCase() }}</div>
          <div class="who-text">
            <strong>{{ auth.operator?.username || '未登录' }}</strong>
            <span>{{ roleLabel }}</span>
          </div>
        </div>
        <button class="logout" title="退出登录" @click="logout"><SvgIcon name="logout" :size="16" /></button>
      </div>
    </aside>

    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.rail {
  width: 216px;
  flex: 0 0 216px;
  background: #fff;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 18px 14px 14px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px 18px;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.28);
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.brand-text strong {
  font-size: 14px;
  letter-spacing: -0.2px;
}
.brand-text span {
  font-size: 11px;
  color: var(--text-dim);
  letter-spacing: 0.4px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 9px;
  color: var(--text-sub);
  font-size: 13.5px;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover {
  background: #f3f6fb;
  color: var(--text);
}
.nav-item.on {
  background: var(--primary-soft);
  color: var(--primary);
  font-weight: 600;
}

.rail-foot {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.who {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #eef2f9;
  color: var(--primary);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: 13px;
  flex: 0 0 30px;
}
.who-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}
.who-text strong {
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who-text span {
  font-size: 11px;
  color: var(--text-dim);
}

.logout {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text-sub);
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  cursor: pointer;
}
.logout:hover {
  color: var(--high);
  border-color: #f5c2c2;
  background: var(--high-soft);
}

.main {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
</style>
