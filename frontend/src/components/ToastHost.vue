<script setup lang="ts">
import { dismissNotification, notifications } from '../notifications'
</script>

<template>
  <div class="toast-host" aria-live="polite" aria-atomic="false">
    <div
      v-for="item in notifications"
      :key="item.id"
      :class="['app-toast', item.kind]"
      :role="item.kind === 'error' ? 'alert' : 'status'"
    >
      <span class="toast-mark" aria-hidden="true">{{ item.kind === 'success' ? '✓' : item.kind === 'error' ? '!' : 'i' }}</span>
      <span>{{ item.message }}</span>
      <button type="button" aria-label="关闭提示" @click="dismissNotification(item.id)">&times;</button>
    </div>
  </div>
</template>
