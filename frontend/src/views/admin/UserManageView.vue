<script setup lang="ts">
import { fetchUsers, updateUserRole } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import type { UserAdmin } from '@/types'
import { ElMessage } from 'element-plus'
import { onMounted, ref, watch } from 'vue'

const auth = useAuthStore()

const users = ref<UserAdmin[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  try {
    const resp = await fetchUsers(page.value, pageSize.value)
    users.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

async function onRoleChange(user: UserAdmin, role: string) {
  try {
    await updateUserRole(user.id, role)
    ElMessage.success(`已将 ${user.username} 的角色改为 ${role}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '修改失败')
    await loadUsers()
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN')
}

onMounted(loadUsers)
watch([page, pageSize], loadUsers)
</script>

<template>
  <div class="admin-page">
    <h2>用户管理</h2>
    <el-table v-loading="loading" :data="users" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="角色" width="140">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            :disabled="row.id === auth.user?.id"
            size="small"
            @change="(role: string) => onRoleChange(row, role)"
          >
            <el-option label="user" value="user" />
            <el-option label="admin" value="admin" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '正常' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
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
.admin-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

h2 {
  margin: 0 0 16px;
  color: #303133;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
