<script setup lang="ts">
import type { MapHeatItem } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  /** 已通过 loadGeoJson 注册的地图名（城市 code） */
  mapName: string
  items: MapHeatItem[]
  title?: string
  selectedName?: string | null
  height?: string
}>()

const emit = defineEmits<{
  select: [item: MapHeatItem]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.mapName || !echarts.getMap(props.mapName)) return

  const values = props.items
    .filter((i) => i.price != null)
    .map((i) => ({
      name: i.region_name,
      value: i.price as number,
      itemStyle:
        i.region_name === props.selectedName
          ? { borderColor: '#303133', borderWidth: 2.5 }
          : undefined,
    }))
  const prices = values.map((v) => v.value)

  chart.setOption(
    {
      title: props.title
        ? { text: props.title, left: 'center', textStyle: { fontSize: 16 } }
        : undefined,
      tooltip: {
        trigger: 'item',
        formatter: (params: any) =>
          Number.isFinite(params.value)
            ? `${params.name}<br/>均价：${params.value} 元/㎡`
            : `${params.name}<br/>暂无数据`,
      },
      visualMap: {
        type: 'continuous',
        min: Math.min(...prices),
        max: Math.max(...prices),
        left: 20,
        bottom: 20,
        text: ['高', '低'],
        inRange: { color: ['#67C23A', '#E6A23C', '#F56C6C'] },
        calculable: true,
      },
      series: [
        {
          type: 'map',
          map: props.mapName,
          label: { show: true, fontSize: 11 },
          emphasis: { label: { show: true }, itemStyle: { areaColor: '#409EFF' } },
          data: values,
        },
      ],
    },
    { notMerge: true },
  )
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params) => {
      const item = props.items.find((i) => i.region_name === params.name)
      if (item && item.price != null) emit('select', item)
    })
    renderChart()
    window.addEventListener('resize', () => chart?.resize())
  }
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})

watch(() => [props.items, props.mapName, props.selectedName, props.title], renderChart, {
  deep: true,
})
</script>

<template>
  <div ref="chartRef" :style="{ width: '100%', height: height ?? '560px' }"></div>
</template>
