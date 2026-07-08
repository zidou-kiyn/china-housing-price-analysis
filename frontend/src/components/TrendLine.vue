<script setup lang="ts">
import type { TrendPoint, TrendSeries } from '@/types'
import * as echarts from 'echarts'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

// 两种模式：series（按源分线，源独立存储后的首选）；data（合并单线，Dashboard 等沿用）
const props = defineProps<{
  title: string
  data?: TrendPoint[]
  series?: TrendSeries[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

// 数据来源 → 图例/口径标签（区分挂牌年度点与月度成交/评估点）
const SOURCE_LABELS: Record<string, string> = {
  creprice: '禧泰 · 月度',
  kaggle_lianjia: '链家 · 月度成交',
  listing_annual_58: '58 · 年度挂牌',
  listing_annual_anjuke: '安居客 · 年度挂牌',
}

const SOURCE_COLORS: Record<string, string> = {
  creprice: '#409EFF',
  kaggle_lianjia: '#67C23A',
  listing_annual_58: '#E6A23C',
  listing_annual_anjuke: '#F56C6C',
}

const hasAnnualListing = computed(() => {
  if (props.series?.length) return props.series.some((s) => s.granularity === 'annual')
  return (props.data ?? []).some((d) => d.source?.startsWith('listing_annual'))
})

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

/** series 模式：统一月份轴，各源一条线；年度源虚线+大标记，跨空档连线不与他源硬连。 */
function buildSplitOption() {
  const seriesList = props.series ?? []
  const months = [...new Set(seriesList.flatMap((s) => s.points.map((p) => p.year_month)))].sort()
  const index = new Map(months.map((m, i) => [m, i]))

  const chartSeries = seriesList.map((s) => {
    const values: (number | null)[] = Array(months.length).fill(null)
    for (const p of s.points) values[index.get(p.year_month)!] = p.supply_price
    const annual = s.granularity === 'annual'
    return {
      name: sourceLabel(s.source),
      type: 'line' as const,
      data: values,
      connectNulls: true, // 各源只连自己的点（年度点相隔 12 个月槽位）
      smooth: !annual,
      symbolSize: annual ? 7 : 4,
      lineStyle: { width: 2, type: annual ? ('dashed' as const) : ('solid' as const) },
      itemStyle: { color: SOURCE_COLORS[s.source] },
    }
  })

  return {
    title: { text: props.title, left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let text = params[0].axisValue
        for (const p of params) {
          if (p.value == null) continue
          text += `<br/>${p.marker} ${p.seriesName}：${p.value} 元/㎡`
        }
        return text
      },
    },
    legend: { bottom: 0, data: chartSeries.map((s) => s.name) },
    xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', name: '元/㎡' },
    series: chartSeries,
    grid: { left: 60, right: 20, bottom: 50, top: 50 },
  }
}

/** data 模式：合并单线（供给价/价值价），tooltip 按点标注来源。 */
function buildMergedOption() {
  const data = props.data ?? []
  const months = data.map((d) => d.year_month)

  return {
    title: { text: props.title, left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let text = params[0].axisValue
        const source = data[params[0].dataIndex]?.source
        if (source) {
          text += `　<span style="color:#909399">${sourceLabel(source)}</span>`
        }
        for (const p of params) {
          text += `<br/>${p.marker} ${p.seriesName}：${p.value ?? '-'} 元/㎡`
        }
        return text
      },
    },
    legend: { bottom: 0, data: ['供给价', '价值价'] },
    xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', name: '元/㎡' },
    series: [
      {
        name: '供给价',
        type: 'line' as const,
        data: data.map((d) => d.supply_price),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#409EFF' },
      },
      {
        name: '价值价',
        type: 'line' as const,
        data: data.map((d) => d.value_price),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' as const },
        itemStyle: { color: '#67C23A' },
      },
    ],
    grid: { left: 60, right: 20, bottom: 50, top: 50 },
  }
}

function renderChart() {
  if (!chart) return
  const splitMode = !!props.series?.length
  if (!splitMode && !props.data?.length) return
  chart.clear()
  chart.setOption(splitMode ? buildSplitOption() : buildMergedOption())
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    renderChart()
    window.addEventListener('resize', () => chart?.resize())
  }
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})

watch(() => [props.data, props.series, props.title], renderChart, { deep: true })
</script>

<template>
  <div>
    <div ref="chartRef" style="width: 100%; height: 350px"></div>
    <p v-if="hasAnnualListing" class="source-note">
      注：虚线为 58/安居客<b>年度挂牌均价</b>（每年一点，落于 12 月），口径略高于成交价，与月度线分开展示。
    </p>
  </div>
</template>

<style scoped>
.source-note {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
  text-align: center;
}
</style>
