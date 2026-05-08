import api from './api';
import { OverviewResponse } from '../types/overview';

export async function fetchOverview(): Promise<OverviewResponse> {
  const response = await api.get<OverviewResponse>('/projects/overview');
  return response.data;
}
