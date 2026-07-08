import * as echarts from 'echarts'

const registeredMaps = new Set<string>()

export async function loadGeoJson(cityCode: string): Promise<boolean> {
  if (registeredMaps.has(cityCode)) return true
  try {
    const res = await fetch(`/geo/${cityCode}.json`)
    if (!res.ok) return false
    const geoJson = await res.json()
    if (!geoJson.features) return false
    echarts.registerMap(cityCode, geoJson as Parameters<typeof echarts.registerMap>[1])
    registeredMaps.add(cityCode)
    return true
  } catch {
    return false
  }
}
