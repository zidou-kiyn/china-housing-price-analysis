<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeIndex = computed(() => route.path)

function onCommand(command: string) {
  if (command === 'logout') {
    auth.logout()
    router.push('/')
  } else if (command === 'admin-users') {
    router.push('/admin/users')
  }
}
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
        <el-menu-item index="/dashboard">大屏</el-menu-item>
      </el-menu>

      <div class="user-area">
        <template v-if="auth.isLoggedIn">
          <el-dropdown @command="onCommand">
            <span class="username">
              {{ auth.user?.username ?? '账号' }}
              <el-icon><i class="el-icon-arrow-down" /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="auth.isAdmin" command="admin-users">用户管理</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <template v-else>
          <RouterLink to="/login" class="auth-link">登录</RouterLink>
          <span class="divider">/</span>
          <RouterLink to="/register" class="auth-link">注册</RouterLink>
        </template>
      </div>
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

.user-area {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.username {
  cursor: pointer;
  color: #409eff;
  font-size: 14px;
  outline: none;
}

.auth-link {
  color: #606266;
  font-size: 14px;
  text-decoration: none;
}

.auth-link:hover {
  color: #409eff;
}

.divider {
  color: #dcdfe6;
}
</style>
