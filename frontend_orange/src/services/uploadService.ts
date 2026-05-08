import api from './api';

export interface UploadPresalesResponse {
  presales_id: string;
  document_id: string;
  chat_history_id: string;
  scanned_requirements?: unknown;
  blind_spots?: unknown[];
  p1_blockers?: unknown[];
  technology_risks?: unknown[];
  kickstart_questions?: unknown[];
  presales_brief?: string;
  status?: string;
  processing_time_seconds?: number;
  analysis_mode?: 'presales';
}

export interface UploadFullResponse {
  message: string;
  document_id: string;
  chat_history_id: string;
  title?: string;
  analysis_mode?: 'full';
}

export type UploadResponse = UploadPresalesResponse | UploadFullResponse;

export async function uploadFiles(
  files: File[],
  analysisMode: 'presales' | 'full' = 'presales',
  onProgress?: (percent: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach(f => form.append('file', f));
  form.append('analysis_mode', analysisMode);

  const { data } = await api.post<UploadResponse>('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
    },
  });
  return data;
}
