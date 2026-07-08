<script setup lang="ts">
import type { TrendPoint } from '@/types'
import * as echarts from 'echarts'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  title: string
  data: TrendPoint[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

// 数据来源 → 口径标注（区分挂牌年度点与月度成交/评估点）
const SOURCE_LABELS: Record<string, string> = {
  listing_annual_58: '58 · 年度挂牌',
  listing_annual_anjuke: '安居客 · 年度挂牌',
  kaggle_lianjia: '链家 · 月度成交',
  creprice: '禧泰 · 月度',
}

const hasAnnualListing = computed(() =>
  props.data.some((d) => d.source?.startsWith('listing_annual')),
)

function renderChart() {
  if (!chart || !props.data.length) return

  const months = props.data.map((d) => d.year_month)

  chart.setOption({
    title: { text: props.title, left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let text = params[0].axisValue
        const source = props.data[params[0].dataIndex]?.source
        if (source) {
          text += `　<span style="color:#909399">${SOURCE_LABELS[source] ?? source}</span>`
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
        type: 'line',
        data: props.data.map((d) => d.supply_price),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#409EFF' },
      },
      {
        name: '价值价',
        type: 'line',
        data: props.data.map((d) => d.value_price),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        itemStyle: { color: '#67C23A' },
      },
    ],
    grid: { left: 60, right: 20, bottom: 50, top: 50 },
  })
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

watch(() => [props.data, props.title], renderChart, { deep: true })
</script>

<template>
  <div>
    <div ref="chartRef" style="width: 100%; height: 350px"></div>
    <p v-if="hasAnnualListing" class="source-note">
      注：部分数据点为 58/安居客<b>年度挂牌均价</b>（落于每年 12 月），口径略高于成交价；悬停可查看各点来源。
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
