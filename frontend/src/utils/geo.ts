import * as echarts from 'echarts'

const registeredMaps = new Set<string>()

/** 加载并注册城市 geojson；文件缺失或非法时返回 false。 */
export async function loadGeoJson(cityCode: string): Promise<boolean> {
  if (registeredMaps.has(cityCode)) return true
  try {
    const resp = await fetch(`/geo/${cityCode}.json`)
    if (!resp.ok) return false
    const geoJson = await resp.json()
    if (!geoJson.features) return false
    echarts.registerMap(cityCode, geoJson)
    registeredMaps.add(cityCode)
    return true
  } catch {
    return false
  }
}
