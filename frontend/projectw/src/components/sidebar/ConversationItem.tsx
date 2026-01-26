import React from 'react';
import { ConversationMetadata } from '../../types/conversation';

interface ConversationItemProps {
  conversation: ConversationMetadata;
  active: boolean;
  isRenaming: boolean;
  newTitle: string;
  activeDropdown: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, e: React.MouseEvent) => void;
  onDelete: (id: string, e: React.MouseEvent) => Promise<void>;
  onTitleChange: (value: string) => void;
  onRenameSave: (id: string, e: React.FormEvent) => void;
  onRenameCancel: () => void;
  onDropdownToggle: (id: string | null) => void;
}

const ConversationItem: React.FC<ConversationItemProps> = ({
  conversation,
  active,
  isRenaming,
  newTitle,
  activeDropdown,
  onSelect,
  onRename,
  onDelete,
  onTitleChange,
  onRenameSave,
  onRenameCancel,
  onDropdownToggle,
}) => {
  return (
    <div className="relative group">
      {isRenaming ? (
        <form 
          className="w-full text-left flex items-center py-2 px-3 rounded-md bg-white/5"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRenameSave(conversation.chat_history_id, e);
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-3 flex-shrink-0 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
      
          <input
            type="text"
            className="flex-1 bg-gray-800 border border-purple-500/50 rounded px-2 py-1 text-sm text-white"
            value={newTitle}
            onChange={(e) => onTitleChange(e.target.value)}
            autoFocus
            onBlur={onRenameCancel}
          />
        </form>
      ) : (
        <>
          <button
            className={`w-full text-left flex items-center py-2 px-3 rounded-md transition-colors relative
              ${active ? 'bg-white/10 text-white' : 'text-gray-400 hover:bg-white/5 hover:text-white'}`}
            onClick={() => onSelect(conversation.chat_history_id)}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            
            <span className="text-sm truncate">
              {conversation.title}
            </span>
          </button>

          {/* Actions dropdown button */}
          <button
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-gray-400 
              hover:bg-white/10 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity
              ${activeDropdown === conversation.chat_history_id ? 'opacity-100 bg-white/10 text-white' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              onDropdownToggle(activeDropdown === conversation.chat_history_id ? null : conversation.chat_history_id);
            }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>

          {/* Dropdown menu */}
          {activeDropdown === conversation.chat_history_id && (
            <div className="absolute right-0 mt-1 w-48 rounded-md bg-gray-800 shadow-lg border border-white/10 z-10">
              <div className="py-1">
                <button 
                  className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-white/5 flex items-center"
                  onClick={(e) => onRename(conversation.chat_history_id, e)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 0L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Rename
                </button>
                <button 
                  className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-white/5 flex items-center"
                  onClick={(e) => onDelete(conversation.chat_history_id, e)}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Delete
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ConversationItem; 