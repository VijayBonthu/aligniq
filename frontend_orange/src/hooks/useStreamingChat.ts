import { useState, useCallback, useRef } from 'react';
import api from '../services/api';

async function attemptTokenRefresh(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return null;
  try {
    const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken });
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('regular_token', data.access_token);
    api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
    return data.access_token;
  } catch {
    return null;
  }
}

function clearAllAuthTokens() {
  ['access_token', 'refresh_token', 'regular_token', 'google_auth_token',
   'user_id', 'user_email', 'user_provider'].forEach(k => localStorage.removeItem(k));
  delete (api.defaults.headers.common as Record<string, string>)['Authorization'];
}

export type StreamEventType =
  | 'stream_start' | 'stream_end' | 'token' | 'content'
  | 'tool_start' | 'tool_result' | 'tool_error' | 'thinking' | 'error';

export interface StreamingState {
  isStreaming: boolean;
  currentContent: string;
  currentTool: string | null;
  toolStatus: 'idle' | 'running' | 'completed' | 'error';
  thinkingMessage: string | null;
  error: string | null;
  toolsUsed: Array<{ tool: string; args?: Record<string, unknown> }>;
}

export interface StreamChatParams {
  chatHistoryId: string;
  userId: string;
  messages: Array<{ role: string; content: string; selected?: boolean }>;
  documentId?: string;
  title?: string;
  token: string;
  onToken?: (token: string, accumulated: string) => void;
  onToolStart?: (toolName: string, args?: Record<string, unknown>) => void;
  onToolResult?: (toolName: string, result: string) => void;
  onComplete?: (content: string, toolsUsed: Array<{ tool: string }>) => void;
  onError?: (error: string) => void;
}

export interface UseStreamingChatReturn extends StreamingState {
  streamChat: (params: StreamChatParams) => Promise<string>;
  cancelStream: () => void;
  resetState: () => void;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080/api/v1';

const initialState: StreamingState = {
  isStreaming: false,
  currentContent: '',
  currentTool: null,
  toolStatus: 'idle',
  thinkingMessage: null,
  error: null,
  toolsUsed: []
};

export function useStreamingChat(): UseStreamingChatReturn {
  const [state, setState] = useState<StreamingState>(initialState);
  const abortControllerRef = useRef<AbortController | null>(null);

  const resetState = useCallback(() => setState(initialState), []);

  const cancelStream = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setState(prev => ({ ...prev, isStreaming: false, currentTool: null, toolStatus: 'idle', thinkingMessage: null }));
  }, []);

  const streamChat = useCallback(async (params: StreamChatParams): Promise<string> => {
    const { chatHistoryId, userId, messages, documentId = '', title = '', token,
            onToken, onToolStart, onToolResult, onComplete, onError } = params;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    setState({ ...initialState, isStreaming: true });

    let accumulatedContent = '';
    const toolsUsed: Array<{ tool: string; args?: Record<string, unknown> }> = [];

    try {
      const makeRequest = (activeToken: string) =>
        fetch(`${API_URL}/chat-with-doc-stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${activeToken}`,
            'Accept': 'text/event-stream'
          },
          body: JSON.stringify({ chat_history_id: chatHistoryId, user_id: userId,
                                  message: messages, document_id: documentId, title }),
          signal: abortControllerRef.current!.signal
        });

      let response = await makeRequest(token);

      if (response.status === 401) {
        const newToken = await attemptTokenRefresh();
        if (!newToken) { clearAllAuthTokens(); window.location.href = '/login'; throw new Error('Session expired'); }
        response = await makeRequest(newToken);
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body reader');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        let eventType = '', eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) { eventType = line.slice(7).trim(); }
          else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
            if (eventType && eventData) {
              try {
                const data = JSON.parse(eventData);
                switch (eventType as StreamEventType) {
                  case 'stream_start':
                    setState(p => ({ ...p, isStreaming: true, thinkingMessage: 'Connected...' })); break;
                  case 'thinking':
                    setState(p => ({ ...p, thinkingMessage: data.message || 'Processing...' })); break;
                  case 'token':
                    accumulatedContent = data.accumulated || (accumulatedContent + (data.token || ''));
                    setState(p => ({ ...p, currentContent: accumulatedContent, thinkingMessage: null }));
                    onToken?.(data.token || '', accumulatedContent); break;
                  case 'content':
                    accumulatedContent += data.content || '';
                    setState(p => ({ ...p, currentContent: accumulatedContent })); break;
                  case 'tool_start':
                    toolsUsed.push({ tool: data.tool || 'unknown', args: data.args || {} });
                    setState(p => ({ ...p, currentTool: data.tool, toolStatus: 'running', toolsUsed: [...toolsUsed] }));
                    onToolStart?.(data.tool || '', data.args || {}); break;
                  case 'tool_result':
                    setState(p => ({ ...p, toolStatus: 'completed', currentTool: null }));
                    onToolResult?.(data.tool || '', data.result || ''); break;
                  case 'tool_error':
                    setState(p => ({ ...p, toolStatus: 'error', currentTool: null })); break;
                  case 'stream_end':
                    accumulatedContent = data.content || accumulatedContent;
                    setState(p => ({ ...p, isStreaming: false, currentContent: accumulatedContent,
                                     currentTool: null, toolStatus: 'idle', thinkingMessage: null,
                                     toolsUsed: data.tools_called || toolsUsed }));
                    onComplete?.(accumulatedContent, data.tools_called || toolsUsed); break;
                  case 'error':
                    setState(p => ({ ...p, isStreaming: false, error: data.message, currentTool: null, toolStatus: 'idle' }));
                    onError?.(data.message || 'Unknown error'); break;
                }
              } catch { /* ignore parse errors */ }
              eventType = ''; eventData = '';
            }
          } else if (line === '') { eventType = ''; eventData = ''; }
        }
      }
      return accumulatedContent;
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') return accumulatedContent;
      const msg = error instanceof Error ? error.message : 'Unknown streaming error';
      setState(p => ({ ...p, isStreaming: false, error: msg }));
      onError?.(msg);
      throw error;
    } finally {
      abortControllerRef.current = null;
    }
  }, []);

  return { ...state, streamChat, cancelStream, resetState };
}

export default useStreamingChat;
