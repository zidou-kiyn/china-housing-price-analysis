import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export const SOURCE_OPTIONS = [
  { value: 'creprice', label: '禧泰 · 月度', desc: '月度实采' },
] as const

export type SourceValue = (typeof SOURCE_OPTIONS)[number]['value']

export const useSourceStore = defineStore('source', () => {
  const current = ref<SourceValue>('creprice')
  const isIndexSource = computed(() => false)
  const isCreprice = computed(() => true)
  const priceSource = computed<string | undefined>(() => 'creprice')
  const label = computed(() => '禧泰 · 月度')

  function setSource(_value: SourceValue) {
    // 单源模式，不做切换
  }

  return { current, isIndexSource, isCreprice, priceSource, label, setSource }
})
