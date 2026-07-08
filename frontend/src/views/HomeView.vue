<script setup lang="ts">
import CitySelect from '@/components/CitySelect.vue'
import DistributionPie from '@/components/DistributionPie.vue'
import DistrictBar from '@/components/DistrictBar.vue'
import IndexTrendLine from '@/components/IndexTrendLine.vue'
import TrendLine from '@/components/TrendLine.vue'
import { usePrice } from '@/composables/usePrice'
import { useSourceStore } from '@/stores/source'
import type { City, DistrictOverviewItem } from '@/types'
import { onMounted, watch } from 'vue'

const source = useSourceStore()
const {
  cities,
  overview,
  cityTrend,
  districtTrend,
  distribution,
  cityIndex,
  districtIndex,
  selectedCity,
  selectedDistrict,
  loading,
  loadCities,
  selectCity,
  selectDistrict,
} = usePrice()

onMounted(() => loadCities())

function onCityChange(city: City) {
  selectCity(city)
}

function onDistrictClick(district: DistrictOverviewItem) {
  selectDistrict(district)
}

// 全局数据源切换：重拉当前城市（含已选区县）数据，源硬隔离下按新源渲染
watch(
  () => source.current,
  () => {
    if (selectedCity.value) selectCity(selectedCity.value)
  },
)
</script>

<template>
  <div class="home">
    <el-container>
      <el-header class="header">
        <span class="header-label">选择城市</span>
        <CitySelect :cities="cities" :model-value="selectedCity" @update:model-value="onCityChange" />
        <el-tag size="small" :type="source.isIndexSource ? 'info' : 'success'" effect="plain">
          数据源：{{ source.label }}
        </el-tag>
      </el-header>

      <el-main v-loading="loading">
        <template v-if="!selectedCity">
          <el-empty description="请选择一个城市开始分析" />
        </template>

        <!-- 指数源：仅走势有意义（指数曲线），概览/分布口径不适用 -->
        <template v-else-if="source.isIndexSource">
          <el-card v-if="cityIndex.length" shadow="hover" class="chart-card">
            <IndexTrendLine :title="`${selectedCity.name} 房价指数走势`" :data="cityIndex" />
          </el-card>
          <el-empty
            v-else
            :description="`${selectedCity.name} 暂无该源（官方指数）数据`"
            :image-size="90"
          />
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="官方指数源仅提供走势（指数单位），区县概览 / 价格分布请切换回价格源查看"
            class="src-alert"
          />
        </template>

        <template v-else>
          <!-- 区县均价柱状图 -->
          <el-card v-if="overview.length" shadow="hover" class="chart-card">
            <DistrictBar :data="overview" @select="onDistrictClick" />
            <p class="chart-hint">点击柱状图查看区县走势</p>
          </el-card>

          <el-row :gutter="20">
            <!-- 城市走势 -->
            <el-col :span="districtTrend.length ? 12 : 24">
              <el-card v-if="cityTrend.length" shadow="hover" class="chart-card">
                <TrendLine :title="`${selectedCity.name} 整体走势`" :series="cityTrend" />
              </el-card>
            </el-col>

            <!-- 区县走势 -->
            <el-col v-if="districtTrend.length && selectedDistrict" :span="12">
              <el-card shadow="hover" class="chart-card">
                <TrendLine :title="`${selectedDistrict.name} 走势`" :series="districtTrend" />
              </el-card>
            </el-col>
          </el-row>

          <!-- 空态：所选源下该城市无价格数据 -->
          <el-empty
            v-if="!overview.length && !cityTrend.length"
            :description="`${selectedCity.name} 在「${source.label}」源下暂无数据`"
            :image-size="90"
          />

          <!-- 价格分布 -->
          <el-card v-if="distribution.length" shadow="hover" class="chart-card">
            <DistributionPie :data="distribution" />
          </el-card>
        </template>
      </el-main>
    </el-container>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.header {
  display: flex;
  align-items: center;
  gap: 12px;
  height: auto;
  padding: 16px 0;
}

.header-label {
  color: #606266;
  font-size: 14px;
}

.chart-card {
  margin-bottom: 20px;
}

.chart-hint {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin: 4px 0 0;
}

.src-alert {
  margin-top: 12px;
}
</style>
