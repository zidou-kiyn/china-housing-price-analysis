<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeIndex = computed(() => route.path)
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <RouterLink to="/" class="logo">城市房价分析系统</RouterLink>
      <el-menu mode="horizontal" :default-active="activeIndex" :ellipsis="false" router class="nav-menu">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/rank">排行榜</el-menu-item>
        <el-menu-item index="/compare">区域对比</el-menu-item>
        <el-menu-item index="/map">地图热力</el-menu-item>
      </el-menu>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
}

.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 32px;
}

.logo {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  text-decoration: none;
  white-space: nowrap;
}

.nav-menu {
  flex: 1;
  border-bottom: none;
}
</style>
