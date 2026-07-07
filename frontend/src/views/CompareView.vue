<script setup lang="ts">
import { fetchCompare } from '@/api/analytics'
import { fetchCities, fetchDistricts } from '@/api/price'
import CitySelect from '@/components/CitySelect.vue'
import CompareLine from '@/components/CompareLine.vue'
import type { City, CompareRegion, District } from '@/types'
import { onMounted, ref, watch } from 'vue'

const MAX_REGIONS = 5

const cities = ref<City[]>([])
const selectedCity = ref<City | null>(null)
const districts = ref<District[]>([])
const selectedIds = ref<number[]>([])
const regions = ref<CompareRegion[]>([])
const loading = ref(false)

async function onCityChange(city: City) {
  selectedCity.value = city
  selectedIds.value = []
  regions.value = []
  districts.value = await fetchDistricts(city.code)
}

async function loadCompare() {
  if (selectedIds.value.length < 2) {
    regions.value = []
    return
  }
  loading.value = true
  try {
    const resp = await fetchCompare({
      region_type: 'district',
      region_ids: selectedIds.value.join(','),
    })
    regions.value = resp.regions
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  cities.value = await fetchCities()
  const qz = cities.value.find((c) => c.code === 'qz') ?? cities.value[0]
  if (qz) await onCityChange(qz)
})

watch(selectedIds, loadCompare)
</script>

<template>
  <div class="compare-page">
    <div class="toolbar">
      <CitySelect :cities="cities" :model-value="selectedCity" @update:model-value="onCityChange" />
      <el-select
        v-model="selectedIds"
        multiple
        :multiple-limit="MAX_REGIONS"
        filterable
        placeholder="选择 2~5 个区县对比"
        style="width: 420px"
      >
        <el-option v-for="d in districts" :key="d.id" :label="d.name" :value="d.id" />
      </el-select>
    </div>

    <el-card v-if="regions.length" v-loading="loading" shadow="hover">
      <CompareLine :regions="regions" />
    </el-card>
    <el-empty v-else description="请选择至少 2 个区县查看走势对比" />
  </div>
</template>

<style scoped>
.compare-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
</style>
