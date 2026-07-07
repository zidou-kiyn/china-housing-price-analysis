import { onUnmounted } from 'vue'

/** 按需启停的轮询：sync(true) 启动、sync(false) 停止，组件卸载自动清理。 */
export function usePolling(callback: () => void | Promise<void>, intervalMs = 3000) {
  let timer: number | null = null

  function sync(active: boolean) {
    if (active && timer === null) {
      timer = window.setInterval(callback, intervalMs)
    } else if (!active && timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(() => {
    if (timer !== null) window.clearInterval(timer)
  })

  return { sync }
}
