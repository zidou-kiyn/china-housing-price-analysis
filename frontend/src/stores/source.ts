import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/**
 * 全局数据源（creprice-first 源硬隔离）。
 *
 * 前 3 项为已登记的 price_snapshot 源（后端 `source` 查询参数取值）；
 * `nbs_index` 是前端合成源——NBS 官方指数走独立的 /prices/index/trend 路径，
 * 不进 ¥/㎡ 端点，仅走势视图有意义。
 */
export const SOURCE_OPTIONS = [
  { value: 'creprice', label: '禧泰 · 月度', desc: '月度实采' },
  { value: 'listing_annual_58', label: '58 · 年度', desc: '年度挂牌' },
  { value: 'kaggle_lianjia', label: '链家 · 历史', desc: '历史成交' },
  { value: 'nbs_index', label: 'NBS · 指数', desc: '官方指数' },
] as const

export type SourceValue = (typeof SOURCE_OPTIONS)[number]['value']

const STORAGE_KEY = 'data_source'
const INDEX_SOURCE = 'nbs_index'
const VALID = new Set(SOURCE_OPTIONS.map((o) => o.value))

export const useSourceStore = defineStore('source', () => {
  const stored = localStorage.getItem(STORAGE_KEY)
  const current = ref<SourceValue>(
    stored && VALID.has(stored as SourceValue) ? (stored as SourceValue) : 'creprice',
  )

  const isIndexSource = computed(() => current.value === INDEX_SOURCE)
  const isCreprice = computed(() => current.value === 'creprice')
  /** 传给 ¥/㎡ 端点的 source；指数源不适用（返回 undefined，调用方应改走空态/指数路径）。 */
  const priceSource = computed<string | undefined>(() =>
    current.value === INDEX_SOURCE ? undefined : current.value,
  )
  const label = computed(
    () => SOURCE_OPTIONS.find((o) => o.value === current.value)?.label ?? current.value,
  )

  function setSource(value: SourceValue) {
    current.value = value
    localStorage.setItem(STORAGE_KEY, value)
  }

  return { current, isIndexSource, isCreprice, priceSource, label, setSource }
})
