<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ChatMessage } from '@/types'

const props = withDefaults(defineProps<{ message: ChatMessage; pending?: boolean }>(), { pending: false })
const open = ref(false)

const name = computed(() => props.message.name || 'tool')
const ok = computed(() => props.message.ok !== false)
const argsText = computed(() => {
  const args = props.message.args
  if (!args || Object.keys(args).length === 0) return '（无参数）'
  return JSON.stringify(args, null, 2)
})
const resultText = computed(() => {
  const raw = props.message.content || ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
})
const preview = computed(() => {
  const text = resultText.value.replace(/\s+/g, ' ')
  if (props.pending) return '执行中…'
  if (!ok.value) return text.slice(0, 90)
  return `已返回 ${text.length} 字符结果`
})
</script>

<template>
  <div class="tool" :class="{ err: !ok, pending }">
    <button class="bar" type="button" @click="open = !open">
      <span class="pulse" :class="{ on: pending, bad: !ok }" />
      <span class="label">
        <span class="muted">{{ pending ? '正在调用' : '已调用' }}</span>
        <b class="mono">{{ name }}</b>
      </span>
      <span class="preview">{{ preview }}</span>
      <span class="chevron" :class="{ open }">›</span>
    </button>

    <div v-show="open" class="detail">
      <div class="section">
        <div class="section-title">入参</div>
        <pre class="code">{{ argsText }}</pre>
      </div>
      <div class="section">
        <div class="section-title">返回</div>
        <pre class="code">{{ resultText }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool {
  border: 1px dashed #d8dfec;
  background: #fbfcfe;
  border-radius: 10px;
  overflow: hidden;
  font-size: 12px;
}
.tool.err {
  border-color: #f3c9c9;
  background: #fffafa;
}

.bar {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}

.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #16a34a;
  flex: 0 0 7px;
}
.pulse.on {
  background: #2563eb;
  animation: blink 1s infinite;
}
.pulse.bad {
  background: #dc2626;
}
@keyframes blink {
  50% {
    opacity: 0.25;
  }
}

.label {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-sub);
}
.label b {
  color: var(--text);
}

.preview {
  flex: 1;
  color: var(--text-dim);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}

.chevron {
  color: var(--text-dim);
  font-size: 15px;
  line-height: 1;
  transition: transform 0.18s;
}
.chevron.open {
  transform: rotate(90deg);
}

.detail {
  border-top: 1px dashed #e1e7f2;
  padding: 8px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.section-title {
  font-size: 10.5px;
  color: var(--text-dim);
  margin-bottom: 3px;
  letter-spacing: 0.3px;
}
.code {
  margin: 0;
  max-height: 200px;
  overflow: auto;
  background: #f4f7fc;
  border-radius: 7px;
  padding: 7px 9px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  color: #33415c;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
