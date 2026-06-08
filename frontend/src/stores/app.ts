import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    serviceName: 'Knowledge Base Agent',
    version: '0.1.0',
  }),
})
