import api from '@/api'
import * as echarts from 'echarts'

const registeredMaps = new Set<string>()

/** 经 geo API 加载并注册城市 geojson（内存缓存）；缺图或非法时返回 false。 */
export async function loadGeoJson(cityCode: string): Promise<boolean> {
  if (registeredMaps.has(cityCode)) return true
  try {
    const geoJson = await api.get<never, { features?: unknown[] }>(`/geo/${cityCode}`)
    if (!geoJson.features) return false
    echarts.registerMap(cityCode, geoJson as Parameters<typeof echarts.registerMap>[1])
    registeredMaps.add(cityCode)
    return true
  } catch {
    return false
  }
}
