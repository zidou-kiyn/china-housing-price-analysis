<script setup lang="ts">
import { deleteUser, fetchUsers, updateUserRole, updateUserStatus } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import type { UserAdmin } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref, watch } from 'vue'

const auth = useAuthStore()

const users = ref<UserAdmin[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const keyword = ref('')
const roleFilter = ref<string>('')
const statusFilter = ref<'' | 'active' | 'inactive'>('')

async function loadUsers() {
  loading.value = true
  try {
    const resp = await fetchUsers(page.value, pageSize.value, {
      keyword: keyword.value.trim(),
      role: roleFilter.value,
      isActive: statusFilter.value === '' ? undefined : statusFilter.value === 'active',
    })
    users.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

/** 筛选条件变更：重置到第 1 页并刷新（page 未变时手动触发）。 */
function onFilterChange() {
  if (page.value === 1) {
    loadUsers()
  } else {
    page.value = 1
  }
}

async function onRoleChange(user: UserAdmin, role: string) {
  try {
    await updateUserRole(user.id, role)
    ElMessage.success(`已将 ${user.username} 的角色改为 ${role}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '修改失败')
  } finally {
    await loadUsers()
  }
}

async function onToggleStatus(user: UserAdmin) {
  const action = user.is_active ? '封禁' : '启用'
  try {
    await updateUserStatus(user.id, !user.is_active)
    ElMessage.success(`已${action}用户 ${user.username}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? `${action}失败`)
  } finally {
    await loadUsers()
  }
}

async function onDelete(user: UserAdmin) {
  try {
    await ElMessageBox.confirm(
      `确定删除用户 ${user.username} 吗？此操作不可恢复。`,
      '删除用户',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteUser(user.id)
    ElMessage.success(`已删除用户 ${user.username}`)
    // 当前页被删空时回退一页
    if (users.value.length === 1 && page.value > 1) {
      page.value -= 1
    } else {
      await loadUsers()
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '删除失败')
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

    <div class="filter-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名/邮箱"
        clearable
        class="filter-keyword"
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      >
        <template #append>
          <el-button @click="onFilterChange">搜索</el-button>
        </template>
      </el-input>
      <el-select
        v-model="roleFilter"
        placeholder="角色"
        clearable
        class="filter-select"
        @change="onFilterChange"
      >
        <el-option label="user" value="user" />
        <el-option label="admin" value="admin" />
      </el-select>
      <el-select
        v-model="statusFilter"
        placeholder="状态"
        clearable
        class="filter-select"
        @change="onFilterChange"
      >
        <el-option label="正常" value="active" />
        <el-option label="禁用" value="inactive" />
      </el-select>
    </div>

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
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            :type="row.is_active ? 'warning' : 'success'"
            size="small"
            :disabled="row.id === auth.user?.id"
            @click="onToggleStatus(row)"
          >
            {{ row.is_active ? '封禁' : '启用' }}
          </el-button>
          <el-button
            type="danger"
            size="small"
            :disabled="row.id === auth.user?.id"
            @click="onDelete(row)"
          >
            删除
          </el-button>
        </template>
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

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.filter-keyword {
  width: 280px;
}

.filter-select {
  width: 120px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
