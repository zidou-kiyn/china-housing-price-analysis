import type { PredictionResponse, RegionType } from '@/types'
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
