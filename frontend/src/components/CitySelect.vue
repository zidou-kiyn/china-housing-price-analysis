<script setup lang="ts">
import type { City } from '@/types'

const props = defineProps<{
  cities: City[]
  modelValue: City | null
}>()

const emit = defineEmits<{
  'update:modelValue': [city: City]
}>()

function handleChange(cityId: number | undefined) {
  if (!cityId) return
  const city = props.cities.find((c) => c.id === cityId)
  if (city) emit('update:modelValue', city)
}
</script>

<template>
  <el-select
    :model-value="modelValue?.id"
    filterable
    placeholder="搜索城市..."
    style="width: 280px"
    @change="handleChange"
  >
    <el-option
      v-for="city in cities"
      :key="city.id"
      :label="city.name"
      :value="city.id"
    />
  </el-select>
</template>
