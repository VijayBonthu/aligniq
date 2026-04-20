/**
 * Custom hook for streaming chat responses via Server-Sent Events (SSE).
 *
 * Provides real-time token streaming, tool execution status, and cancellation support.
 */

import { useState, useCallback, useRef } from 'react';
import api from '../services/api';

// Attempt a token refresh using the shared api instance; returns the new access token or null.
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

// SSE Event types from backend
export type StreamEventType =
  | 'stream_start'
  | 'stream_end'
  | 'token'
  | 'content'
  | 'tool_start'
  | 'tool_result'
  | 'tool_error'
  | 'thinking'
  | 'error';

export interface StreamEvent {
  event: StreamEventType;
  data: Record<string, unknown>;
}

export interface StreamingState {
  isStreaming: boolean;
  currentContent: string;
  currentTool: string | null;
  toolStatus: 'idle' | 'running' | 'completed' | 'error';
  thinkingMessage: string | null;
  error: string | null;
  toolsUsed: Array<{ tool: string; args?: Record<string, unknown> }>;
}

export interface UseStreamingChatReturn extends StreamingState {
  streamChat: (params: StreamChatParams) => Promise<string>;
  cancelStream: () => void;
  resetState: () => void;
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

  const resetState = useCallback(() => {
    setState(initialState);
  }, []);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setState(prev => ({
      ...prev,
      isStreaming: false,
      currentTool: null,
      toolStatus: 'idle',
      thinkingMessage: null
    }));
  }, []);

  const streamChat = useCallback(async (params: StreamChatParams): Promise<string> => {
    const {
      chatHistoryId,
      userId,
      messages,
      documentId = '',
      title = '',
      token,
      onToken,
      onToolStart,
      onToolResult,
      onComplete,
      onError
    } = params;

    // Cancel any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();

    // Reset state for new stream
    setState({
      ...initialState,
      isStreaming: true
    });

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
          body: JSON.stringify({
            chat_history_id: chatHistoryId,
            user_id: userId,
            message: messages,
            document_id: documentId,
            title: title
          }),
          signal: abortControllerRef.current!.signal
        });

      let response = await makeRequest(token);

      // On 401, refresh the token and retry once
      if (response.status === 401) {
        const newToken = await attemptTokenRefresh();
        if (!newToken) {
          clearAllAuthTokens();
          window.location.href = '/login';
          throw new Error('Session expired. Please log in again.');
        }
        response = await makeRequest(newToken);
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body reader available');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        let currentEventType = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);

            if (currentEventType && currentData) {
              try {
                const data = JSON.parse(currentData);

                switch (currentEventType as StreamEventType) {
                  case 'stream_start':
                    setState(prev => ({
                      ...prev,
                      isStreaming: true,
                      thinkingMessage: 'Connected...'
                    }));
                    break;

                  case 'thinking':
                    setState(prev => ({
                      ...prev,
                      thinkingMessage: data.message || 'Processing...'
                    }));
                    break;

                  case 'token':
                    accumulatedContent = data.accumulated || (accumulatedContent + (data.token || ''));
                    setState(prev => ({
                      ...prev,
                      currentContent: accumulatedContent,
                      thinkingMessage: null
                    }));
                    onToken?.(data.token || '', accumulatedContent);
                    break;

                  case 'content':
                    accumulatedContent += data.content || '';
                    setState(prev => ({
                      ...prev,
                      currentContent: accumulatedContent
                    }));
                    break;

                  case 'tool_start':
                    const toolName = data.tool || 'unknown';
                    const toolArgs = data.args || {};
                    toolsUsed.push({ tool: toolName, args: toolArgs });
                    setState(prev => ({
                      ...prev,
                      currentTool: toolName,
                      toolStatus: 'running',
                      toolsUsed: [...toolsUsed]
                    }));
                    onToolStart?.(toolName, toolArgs);
                    break;

                  case 'tool_result':
                    setState(prev => ({
                      ...prev,
                      toolStatus: 'completed',
                      currentTool: null
                    }));
                    onToolResult?.(data.tool || '', data.result || '');
                    break;

                  case 'tool_error':
                    setState(prev => ({
                      ...prev,
                      toolStatus: 'error',
                      currentTool: null
                    }));
                    break;

                  case 'stream_end':
                    accumulatedContent = data.content || accumulatedContent;
                    setState(prev => ({
                      ...prev,
                      isStreaming: false,
                      currentContent: accumulatedContent,
                      currentTool: null,
                      toolStatus: 'idle',
                      thinkingMessage: null,
                      toolsUsed: data.tools_called || toolsUsed
                    }));
                    onComplete?.(accumulatedContent, data.tools_called || toolsUsed);
                    break;

                  case 'error':
                    const errorMsg = data.message || 'Unknown error';
                    setState(prev => ({
                      ...prev,
                      isStreaming: false,
                      error: errorMsg,
                      currentTool: null,
                      toolStatus: 'idle'
                    }));
                    onError?.(errorMsg);
                    break;
                }
              } catch (parseError) {
                console.error('Failed to parse SSE data:', parseError, currentData);
              }

              // Reset for next event
              currentEventType = '';
              currentData = '';
            }
          } else if (line === '') {
            // Empty line marks end of an event
            currentEventType = '';
            currentData = '';
          }
        }
      }

      return accumulatedContent;

    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Stream was cancelled - not an error
        return accumulatedContent;
      }

      const errorMessage = error instanceof Error ? error.message : 'Unknown streaming error';
      setState(prev => ({
        ...prev,
        isStreaming: false,
        error: errorMessage
      }));
      onError?.(errorMessage);
      throw error;

    } finally {
      abortControllerRef.current = null;
    }
  }, []);

  return {
    ...state,
    streamChat,
    cancelStream,
    resetState
  };
}

export default useStreamingChat;
