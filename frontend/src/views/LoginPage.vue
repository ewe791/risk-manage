<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import SvgIcon from '@/components/SvgIcon.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = ref({ username: 'admin', password: 'Admin@12345' })
const loading = ref(false)

const ACCOUNTS = [
  { username: 'admin', password: 'Admin@12345', label: '风控管理员' },
  { username: 'reviewer', password: 'Reviewer@12345', label: '风控审核员' },
  { username: 'viewer', password: 'Viewer@12345', label: '数据查看人' }
]

function fill(account: (typeof ACCOUNTS)[number]) {
  form.value.username = account.username
  form.value.password = account.password
}

async function submit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名与密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.value.username, form.value.password)
    const redirect = (route.query.redirect as string) || '/workbench'
    router.push(redirect === '/workbench' ? '/check' : redirect)
  } catch (error: any) {
    ElMessage.error(error?.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <section class="intro">
      <div class="intro-inner">
        <div class="badge"><SvgIcon name="shield" :size="16" /> 电商风险控制系统 2.3</div>
        <h1>风控 Agent<br />让规则、特征与决策在对话里跑起来</h1>
        <p class="sub">25 个风控特征 · 24 条可编排规则 · 自动建案 · 全链路留痕</p>

        <ul class="points">
          <li>
            <strong>一句话发起检查</strong>
            <span>「支付环节查一下 U1001 的 O2001」→ 评分、等级、建议、命中规则一次给全</span>
          </li>
          <li>
            <strong>规则可即时启停</strong>
            <span>停用 R05 后重查同一订单，评分从 93 降到 63，决策自动从拒绝转放行</span>
          </li>
          <li>
            <strong>每个结论都有依据</strong>
            <span>特征快照 + 规则命中 + 工具调用日志，全部可回溯</span>
          </li>
        </ul>
      </div>
    </section>

    <section class="panel">
      <div class="form-wrap">
        <h2>登录控制台</h2>
        <p class="hint">选择演示账号一键填充</p>

        <div class="accounts">
          <button
            v-for="account in ACCOUNTS"
            :key="account.username"
            type="button"
            class="account"
            :class="{ on: form.username === account.username }"
            @click="fill(account)"
          >
            <strong>{{ account.label }}</strong>
            <span class="mono">{{ account.username }}</span>
          </button>
        </div>

        <label class="field">
          <span>用户名</span>
          <input v-model="form.username" autocomplete="username" placeholder="请输入用户名" />
        </label>
        <label class="field">
          <span>密码</span>
          <input
            v-model="form.password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            @keyup.enter="submit"
          />
        </label>

        <button class="submit" :disabled="loading" @click="submit">
          {{ loading ? '登录中…' : '登录' }}
        </button>

        <p class="foot">JWT 身份由后端签发，操作员 ID 不出现在 Agent 工具参数中。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  height: 100vh;
  background: #fff;
}

.intro {
  background: radial-gradient(1200px 600px at 10% 10%, #1e3a8a 0%, #111c3a 45%, #0b1226 100%);
  color: #e8eefc;
  display: flex;
  align-items: center;
  padding: 0 8%;
  position: relative;
  overflow: hidden;
}

.intro::after {
  content: '';
  position: absolute;
  width: 520px;
  height: 520px;
  right: -180px;
  bottom: -200px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(79, 70, 229, 0.45), transparent 65%);
}

.intro-inner {
  position: relative;
  z-index: 1;
  max-width: 520px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  padding: 5px 11px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.07);
  color: #c7d6f5;
}

h1 {
  font-size: 30px;
  line-height: 1.36;
  margin: 22px 0 14px;
  letter-spacing: -0.8px;
  font-weight: 650;
}

.sub {
  color: #9fb3d9;
  font-size: 13.5px;
  margin: 0 0 30px;
}

.points {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.points li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 16px;
  border-left: 2px solid rgba(99, 130, 220, 0.5);
}
.points strong {
  font-size: 13.5px;
  color: #ffffff;
  font-weight: 600;
}
.points span {
  font-size: 12.5px;
  color: #93a8cc;
  line-height: 1.6;
}

.panel {
  display: grid;
  place-items: center;
  padding: 40px;
}

.form-wrap {
  width: 100%;
  max-width: 356px;
}

h2 {
  font-size: 22px;
  margin: 0 0 6px;
  letter-spacing: -0.4px;
}
.hint {
  color: var(--text-dim);
  font-size: 12.5px;
  margin: 0 0 20px;
}

.accounts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 20px;
}
.account {
  text-align: left;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #fff;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: all 0.15s;
}
.account strong {
  font-size: 13px;
  font-weight: 600;
}
.account .mono {
  color: var(--text-dim);
}
.account:hover {
  border-color: #c3d2f5;
  background: #f8faff;
}
.account.on {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.field {
  display: block;
  margin-bottom: 14px;
}
.field span {
  display: block;
  font-size: 12.5px;
  color: var(--text-sub);
  margin-bottom: 6px;
}
.field input {
  width: 100%;
  height: 40px;
  border-radius: 9px;
  border: 1px solid var(--border);
  padding: 0 12px;
  font-size: 14px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.field input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.submit {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: 9px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 6px;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
}
.submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.foot {
  margin-top: 18px;
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .login {
    grid-template-columns: 1fr;
  }
  .intro {
    display: none;
  }
}
</style>
