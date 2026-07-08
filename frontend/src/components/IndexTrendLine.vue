<script setup lang="ts">
import type { IndexTrendPoint } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

// NBS 房价指数走势（单位=指数非价格，基准=100 上月/上年）。与 ¥/㎡ 走势分开渲染。
const props = defineProps<{ title: string; data: IndexTrendPoint[] }>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.data.length) return
  const months = props.data.map((d) => d.year_month)
  chart.clear()
  chart.setOption({
    title: { text: props.title, left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) =>
        `${params[0].axisValue}<br/>${params[0].marker} 指数：${params[0].value}`,
    },
    xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', name: '指数', scale: true },
    series: [
      {
        name: '房价指数',
        type: 'line',
        data: props.data.map((d) => d.index_value),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#909399' },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ yAxis: 100 }],
          lineStyle: { type: 'dashed', color: '#c0c4cc' },
          label: { formatter: '基准 100' },
        },
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
    <p class="source-note">
      注：NBS 官方<b>房价指数</b>（二手房环比，基准 100），单位为指数非价格，与 ¥/㎡ 走势口径不同。
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
