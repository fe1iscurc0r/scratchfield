<script setup lang="ts">
import { Button, ToggleSwitch } from 'primevue'
import { ref } from 'vue'

const props = defineProps<{
  postId: string
  replyToId?: string
  placeholder?: string
}>()

const emit = defineEmits<{
  submit: [payload: { content: string, wantToMeet: boolean, replyToId?: string }]
}>()

const content = ref('')
const wantToMeet = ref(false)
const submitting = ref(false)

async function handleSubmit() {
  if (!content.value.trim())
    return
  submitting.value = true
  try {
    emit('submit', {
      content: content.value.trim(),
      wantToMeet: wantToMeet.value,
      replyToId: props.replyToId,
    })
    content.value = ''
    wantToMeet.value = false
  }
  finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="reply-input flex flex-col gap-2">
    <textarea
      v-model="content"
      :placeholder="placeholder || '写下你的回复...'"
      rows="2"
      class="reply-textarea"
      @keydown.enter.meta="handleSubmit"
      @keydown.enter.ctrl="handleSubmit"
    />
    <div class="flex items-center justify-between">
      <label class="flex items-center gap-2 cursor-pointer">
        <ToggleSwitch v-model="wantToMeet" />
        <span class="text-xs" :class="wantToMeet ? 'text-#d4af37' : 'text-white/30'">想要认识!</span>
      </label>
      <Button
        label="发送"
        size="small"
        :loading="submitting"
        :disabled="!content.trim()"
        @click="handleSubmit"
      />
    </div>
  </div>
</template>

<style scoped>
.reply-textarea {
  width: 100%;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  padding: 8px 10px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  line-height: 1.5;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
}
.reply-textarea:focus {
  border-color: rgba(212, 175, 55, 0.4);
}
.reply-textarea::placeholder {
  color: rgba(255, 255, 255, 0.2);
}
</style>
