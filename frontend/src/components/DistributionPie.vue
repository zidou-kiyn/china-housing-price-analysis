<script setup lang="ts">
import type { DistributionItem } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  data: DistributionItem[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.data.length) return

  const pieData = props.data.map((d) => ({
    name: `${d.price_range_low}-${d.price_range_high}`,
    value: Number(d.percentage) || 0,
  }))

  chart.setOption({
    title: { text: '价格区间分布', left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'item',
      formatter: '{b} 元/㎡<br/>占比 {d}%',
    },
    legend: { orient: 'vertical', left: 'left', top: 'middle' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['60%', '55%'],
        data: pieData,
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } },
        label: { show: false },
      },
    ],
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

watch(() => props.data, renderChart, { deep: true })
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 350px"></div>
</template>
