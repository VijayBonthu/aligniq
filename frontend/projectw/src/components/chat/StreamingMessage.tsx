/**
 * StreamingMessage component for displaying streaming chat responses.
 *
 * Shows real-time token streaming, tool execution status indicators,
 * thinking dots, and a streaming cursor.
 */

import React, { useMemo } from 'react';
import { marked } from 'marked';

interface StreamingMessageProps {
  content: string;
  isStreaming: boolean;
  currentTool?: string | null;
  toolStatus?: 'idle' | 'running' | 'completed' | 'error';
  thinkingMessage?: string | null;
  toolsUsed?: Array<{ tool: string; args?: Record<string, unknown> }>;
  sanitize?: (html: string) => string;
}

// Tool display name mapping
const toolDisplayNames: Record<string, string> = {
  search_document: 'Searching document',
  get_pending_changes: 'Loading pending changes',
  add_pending_change: 'Adding change',
  remove_pending_change: 'Removing change',
  clear_all_pending_changes: 'Clearing all changes',
  regenerate_report: 'Regenerating report',
  rollback_report: 'Rolling back report',
  get_report_section: 'Reading report section',
  compare_report_versions: 'Comparing versions',
  get_risks_and_mitigations: 'Analyzing risks',
  analyze_cost_reduction: 'Analyzing costs',
  analyze_timeline_acceleration: 'Analyzing timeline',
  suggest_optimization: 'Finding optimizations'
};

const getToolDisplayName = (toolName: string): string => {
  return toolDisplayNames[toolName] || toolName.replace(/_/g, ' ');
};

export const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  isStreaming,
  currentTool,
  toolStatus = 'idle',
  thinkingMessage,
  toolsUsed = [],
  sanitize
}) => {
  // Memoize markdown parsing to prevent re-renders on each token
  const renderedHtml = useMemo(() => {
    if (!content) return '';
    const rawHtml = marked.parse(content);
    const htmlString = typeof rawHtml === 'string' ? rawHtml : String(rawHtml);
    // Apply sanitization if provided (DOMPurify)
    return sanitize ? sanitize(htmlString) : htmlString;
  }, [content, sanitize]);

  return (
    <div className="flex-1 flex flex-col space-y-2">
      {/* Thinking indicator */}
      {thinkingMessage && !currentTool && (
        <div className="flex items-center gap-2 px-3 py-2 bg-purple-500/10 border border-purple-500/20 rounded-lg text-sm">
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-purple-300">{thinkingMessage}</span>
        </div>
      )}

      {/* Tool status indicator */}
      {currentTool && toolStatus === 'running' && (
        <div className="flex items-center gap-2 px-3 py-2 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm">
          <div className="animate-spin h-4 w-4 border-2 border-blue-400 border-t-transparent rounded-full" />
          <span className="text-blue-300">
            {getToolDisplayName(currentTool)}
          </span>
        </div>
      )}

      {/* Tools used summary (collapsed) */}
      {toolsUsed.length > 0 && !isStreaming && (
        <div className="flex flex-wrap gap-1 text-xs">
          {toolsUsed.map((tool, index) => (
            <span
              key={`${tool.tool}-${index}`}
              className="px-2 py-0.5 bg-green-500/10 border border-green-500/20 rounded-full text-green-400"
            >
              {getToolDisplayName(tool.tool)}
            </span>
          ))}
        </div>
      )}

      {/* Message content with streaming cursor */}
      {content && (
        <div className="prose prose-invert text-gray-100 max-w-none break-words text-sm md:text-base
                        [&_pre]:overflow-x-auto [&_pre]:max-w-full [&_pre]:rounded-lg [&_pre]:bg-black/30 [&_pre]:p-3
                        [&_code]:break-all [&_code]:bg-black/20 [&_code]:px-1 [&_code]:rounded
                        [&_table]:block [&_table]:overflow-x-auto [&_table]:w-max [&_table]:max-w-full
                        [&_img]:max-w-full [&_img]:h-auto">
          <div dangerouslySetInnerHTML={{ __html: renderedHtml }} />
          {/* Streaming cursor */}
          {isStreaming && (
            <span className="inline-block w-2 h-5 ml-0.5 bg-purple-400 animate-pulse align-middle" />
          )}
        </div>
      )}

      {/* Empty state with streaming cursor */}
      {!content && isStreaming && !thinkingMessage && !currentTool && (
        <div className="flex items-center">
          <span className="inline-block w-2 h-5 bg-purple-400 animate-pulse" />
        </div>
      )}
    </div>
  );
};

export default StreamingMessage;
