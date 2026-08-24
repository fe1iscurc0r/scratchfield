<script setup lang="ts">
import Button from 'primevue/button'
import { trackTelemetry } from '@/utils/telemetry'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ success: [], skip: [] }>()

function handleEnter() {
  trackTelemetry('login_skip', { mode: 'quick-enter' })
  emit('skip')
}
</script>

<template>
  <Transition name="login-fade">
    <div v-if="visible" class="login-overlay">
      <div class="login-card">
        <h2 class="login-title">陆墨</h2>
        <Button
          label="进 入"
          class="login-btn"
          @click="handleEnter"
        />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.login-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.login-card {
  width: 280px;
  padding: 2.5rem 2rem;
  border: 1px solid rgba(212, 175, 55, 0.5);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.92);
  box-shadow: 0 0 40px rgba(212, 175, 55, 0.1);
  text-align: center;
}

.login-title {
  margin: 0 0 1.5rem;
  font-size: 1.5rem;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.9);
  letter-spacing: 0.1em;
}

.login-btn {
  width: 100%;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.8), rgba(180, 140, 30, 0.8));
  border: none;
  color: #1a1206;
  font-weight: 600;
}

.login-btn:hover {
  background: linear-gradient(135deg, rgba(212, 175, 55, 1), rgba(180, 140, 30, 1));
}

.login-fade-enter-active {
  transition: opacity 0.3s ease;
}

.login-fade-enter-from {
  opacity: 0;
}

.login-fade-leave-active {
  transition: opacity 0.3s ease;
}

.login-fade-leave-to {
  opacity: 0;
}
</style>
