import React from 'react';
import { GroupedConversations } from '../../types/conversation';
import ConversationItem from './ConversationItem';

interface ConversationListProps {
  groupedConversations: GroupedConversations;
  activeConversationId: string | null;
  renamingConversation: string | null;
  newTitle: string;
  activeDropdown: string | null;
  onSelectConversation: (id: string) => void;
  onRenameStart: (id: string, e: React.MouseEvent) => void;
  onRenameSave: (id: string, e: React.FormEvent) => void;
  onRenameCancel: () => void;
  onTitleChange: (value: string) => void;
  onDeleteConversation: (id: string, e: React.MouseEvent) => Promise<void>;
  onDropdownToggle: (id: string | null) => void;
}

const ConversationList: React.FC<ConversationListProps> = ({
  groupedConversations,
  activeConversationId,
  renamingConversation,
  newTitle,
  activeDropdown,
  onSelectConversation,
  onRenameStart,
  onRenameSave,
  onRenameCancel,
  onTitleChange,
  onDeleteConversation,
  onDropdownToggle,
}) => {
  return (
    <div className="flex-grow overflow-y-auto">
      <div className="px-4">
        <h3 className="text-xs font-medium text-gray-300 mb-2">
          Recent conversations
        </h3>
        
        {/* Conversations grouped by time period */}
        {Object.entries(groupedConversations)
          .filter(([_, convs]) => convs.length > 0)
          .map(([period, convs]) => (
            <div key={period} className="mb-4">
              <h4 className="text-xs text-gray-500 mb-1">
                {period.charAt(0).toUpperCase() + period.slice(1)}
              </h4>
              
              <div className="space-y-1">
                {convs.map(conversation => (
                  <ConversationItem
                    key={conversation.chat_history_id}
                    conversation={conversation}
                    active={activeConversationId === conversation.chat_history_id}
                    isRenaming={renamingConversation === conversation.chat_history_id}
                    newTitle={newTitle}
                    activeDropdown={activeDropdown}
                    onSelect={onSelectConversation}
                    onRename={onRenameStart}
                    onDelete={onDeleteConversation}
                    onTitleChange={onTitleChange}
                    onRenameSave={onRenameSave}
                    onRenameCancel={onRenameCancel}
                    onDropdownToggle={onDropdownToggle}
                  />
                ))}
              </div>
            </div>
          ))}
        
        {/* Show message if no conversations */}
        {Object.values(groupedConversations).flat().length === 0 && (
          <div className="text-center py-4 text-gray-500">
            <p>No conversations yet</p>
            <p className="text-xs mt-1">Click "New Chat" to get started</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConversationList; 