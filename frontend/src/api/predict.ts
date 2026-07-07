import type { AdminJob, ModelVersion, PredictionResponse, RegionType } from '@/types'
import api from './index'

export function fetchPrediction(
  regionType: RegionType,
  regionId: number,
  monthsAhead = 3,
): Promise<PredictionResponse> {
  return api.get(`/predict/${regionId}`, {
    params: { region_type: regionType, months_ahead: monthsAhead },
  })
}

// ---- 模型管理（admin） ----

export function fetchModelVersions(): Promise<ModelVersion[]> {
  return api.get('/admin/predict/models')
}

export function setActiveModel(modelName: string, version: string): Promise<ModelVersion[]> {
  return api.put('/admin/predict/models/active', { model_name: modelName, version })
}

export function submitTrain(payload: {
  model_name: string
  city_codes?: string[]
}): Promise<AdminJob> {
  return api.post('/admin/predict/train', payload)
}
