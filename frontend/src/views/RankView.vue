<script setup lang="ts">
import { fetchRank } from '@/api/analytics'
import { fetchCities } from '@/api/price'
import CitySelect from '@/components/CitySelect.vue'
import type { City, PriceType, RankItem, RegionType } from '@/types'
import { onMounted, ref, watch } from 'vue'

const regionType = ref<RegionType>('district')
const cities = ref<City[]>([])
const selectedCity = ref<City | null>(null)
const items = ref<RankItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const sortBy = ref<PriceType>('supply_price')
const sortOrder = ref<'asc' | 'desc'>('desc')
const loading = ref(false)

async function loadRank() {
  if (regionType.value === 'district' && !selectedCity.value) return
  loading.value = true
  try {
    const resp = await fetchRank({
      region_type: regionType.value,
      city_code: regionType.value === 'district' ? selectedCity.value!.code : undefined,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

function onSortChange({ prop, order }: { prop: string; order: string | null }) {
  if (!order) return
  sortBy.value = prop as PriceType
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  page.value = 1
  loadRank()
}

function pctClass(value: number | null): string {
  if (value == null) return ''
  return value > 0 ? 'pct-up' : value < 0 ? 'pct-down' : ''
}

function formatPct(value: number | null): string {
  if (value == null) return '-'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatPrice(value: number | null): string {
  return value == null ? '-' : value.toLocaleString()
}

onMounted(async () => {
  cities.value = await fetchCities()
  selectedCity.value = cities.value.find((c) => c.code === 'qz') ?? cities.value[0] ?? null
  await loadRank()
})

watch([regionType, selectedCity, page, pageSize], loadRank)
</script>

<template>
  <div class="rank-page">
    <div class="toolbar">
      <el-radio-group v-model="regionType">
        <el-radio-button value="district">区县榜</el-radio-button>
        <el-radio-button value="city">城市榜</el-radio-button>
      </el-radio-group>
      <CitySelect
        v-if="regionType === 'district'"
        :cities="cities"
        :model-value="selectedCity"
        @update:model-value="(c: City) => (selectedCity = c)"
      />
    </div>

    <el-table
      v-loading="loading"
      :data="items"
      :default-sort="{ prop: 'supply_price', order: 'descending' }"
      stripe
      @sort-change="onSortChange"
    >
      <el-table-column type="index" label="排名" width="70">
        <template #default="{ $index }">{{ (page - 1) * pageSize + $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="region_name" label="区域" min-width="120" />
      <el-table-column prop="supply_price" label="供给价 (元/㎡)" sortable="custom" min-width="130">
        <template #default="{ row }">{{ formatPrice(row.supply_price) }}</template>
      </el-table-column>
      <el-table-column prop="value_price" label="价值价 (元/㎡)" sortable="custom" min-width="130">
        <template #default="{ row }">{{ formatPrice(row.value_price) }}</template>
      </el-table-column>
      <el-table-column prop="mom_pct" label="环比" min-width="90">
        <template #default="{ row }">
          <span :class="pctClass(row.mom_pct)">{{ formatPct(row.mom_pct) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="yoy_pct" label="同比" min-width="90">
        <template #default="{ row }">
          <span :class="pctClass(row.yoy_pct)">{{ formatPct(row.yoy_pct) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="year_month" label="数据月份" min-width="100">
        <template #default="{ row }">{{ row.year_month ?? '-' }}</template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      class="pagination"
    />
  </div>
</template>

<style scoped>
.rank-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.pct-up {
  color: #f56c6c;
}

.pct-down {
  color: #67c23a;
}
</style>
