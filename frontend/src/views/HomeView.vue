<script setup lang="ts">
import CitySelect from '@/components/CitySelect.vue'
import DistributionPie from '@/components/DistributionPie.vue'
import DistrictBar from '@/components/DistrictBar.vue'
import TrendLine from '@/components/TrendLine.vue'
import { usePrice } from '@/composables/usePrice'
import type { City, DistrictOverviewItem } from '@/types'
import { onMounted } from 'vue'

const {
  cities,
  overview,
  cityTrend,
  districtTrend,
  distribution,
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
</script>

<template>
  <div class="home">
    <el-container>
      <el-header class="header">
        <span class="header-label">选择城市</span>
        <CitySelect :cities="cities" :model-value="selectedCity" @update:model-value="onCityChange" />
      </el-header>

      <el-main v-loading="loading">
        <template v-if="!selectedCity">
          <el-empty description="请选择一个城市开始分析" />
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
                <TrendLine :title="`${selectedCity.name} 整体走势`" :data="cityTrend" />
              </el-card>
            </el-col>

            <!-- 区县走势 -->
            <el-col v-if="districtTrend.length && selectedDistrict" :span="12">
              <el-card shadow="hover" class="chart-card">
                <TrendLine :title="`${selectedDistrict.name} 走势`" :data="districtTrend" />
              </el-card>
            </el-col>
          </el-row>

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
</style>
