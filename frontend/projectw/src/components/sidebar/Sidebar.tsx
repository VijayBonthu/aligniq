import React, { useState, useEffect } from 'react';
import ProfileMenu from './ProfileMenu';
import NewChatButton from './NewChatButton';
import ConversationList from './ConversationList';
import { GroupedConversations } from '../../types/conversation';
import * as conversationService from '../../services/conversationService';
import { toast } from 'react-hot-toast';

interface SidebarProps {
  expanded: boolean;
  toggleExpanded: () => void;
  onSelectConversation: (conversation: any) => void;
  onNewChat: () => void;
  logout: () => void;
  isMobile: boolean;
  activeConversationId: string | null;
  groupedConversations: GroupedConversations;
  onRefreshConversations?: () => Promise<void>;
}

const Sidebar: React.FC<SidebarProps> = ({
  expanded,
  toggleExpanded,
  onSelectConversation,
  onNewChat,
  logout,
  isMobile,
  activeConversationId,
  groupedConversations,
  onRefreshConversations
}) => {
  // Local state
  const [renamingConversation, setRenamingConversation] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Use the parent's refresh function if provided, otherwise use local
  const fetchConversations = async () => {
    if (onRefreshConversations) {
      await onRefreshConversations();
    } else {
      try {
        setLoading(true);
        const grouped = await conversationService.fetchConversations();
        // We don't set state here anymore as it should be managed by the parent
      } catch (error) {
        console.error('Error fetching conversations:', error);
        toast.error('Failed to load conversations');
      } finally {
        setLoading(false);
      }
    }
  };

  // Handle selecting a conversation
  const handleSelectConversation = async (chatHistoryId: string) => {
    try {
      const conversation = await conversationService.getConversation(chatHistoryId);
      onSelectConversation(conversation);
      
      // Close sidebar on mobile
      if (isMobile && expanded) {
        toggleExpanded();
      }
    } catch (error) {
      console.error('Error selecting conversation:', error);
      toast.error('Failed to load conversation');
    }
  };

  // Start renaming a conversation
  const handleRenameStart = (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    
    // Set the conversation as being renamed and show input
    setRenamingConversation(chatId);
    
    // Get current title to pre-fill
    const conversation = Object.values(groupedConversations)
      .flat()
      .find(conv => conv.chat_history_id === chatId);
      
    if (conversation) {
      setNewTitle(conversation.title);
    }
    
    // Close dropdown
    setActiveDropdown(null);
  };

  // Save the new title
  const handleRenameSave = async (chatId: string, e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!newTitle.trim()) return;
    
    try {
      await conversationService.renameConversation(chatId, newTitle.trim());
      
      // Update done through parent refresh now
      if (onRefreshConversations) {
        await onRefreshConversations();
      }
      
      setRenamingConversation(null);
      setNewTitle('');
      
      toast.success('Conversation renamed');
    } catch (error) {
      console.error('Error renaming conversation:', error);
      toast.error('Failed to rename conversation');
    }
  };

  // Cancel renaming
  const handleRenameCancel = () => {
    setRenamingConversation(null);
    setNewTitle('');
  };

  // Delete a conversation
  const handleDeleteConversation = async (chatId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    
    try {
      await conversationService.deleteConversation(chatId);
      
      // Update done through parent refresh now
      if (onRefreshConversations) {
        await onRefreshConversations();
      }
      
      setActiveDropdown(null);
      
      // If this was the active conversation, go back to upload UI
      if (activeConversationId === chatId) {
        onNewChat();
      }
      
      toast.success('Conversation deleted');
    } catch (error) {
      console.error('Error deleting conversation:', error);
      toast.error('Failed to delete conversation');
    }
  };

  return (
    <>
      {/* Mobile overlay - only show when sidebar is expanded on mobile */}
      {isMobile && expanded && (
        <div 
          className="fixed inset-0 bg-black/50 z-20"
          onClick={toggleExpanded}
        />
      )}
      
      {/* Sidebar - always visible but position differs on mobile */}
      <aside 
        className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-[#1c1b3b] border-r border-white/10 transition-all duration-300 ease-in-out overflow-hidden
          ${expanded ? (isMobile ? 'w-64' : 'w-64') : (isMobile ? 'w-0' : 'w-16')}`}
      >
        <div className="flex flex-col h-full">
          {expanded ? (
            // EXPANDED SIDEBAR CONTENT
            <>
              {/* Logo + brand */}
              <div className="flex-none p-3 border-b border-white/10">
                <div className="flex items-center">
                  <div className="h-8 w-8 rounded-md bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center">
                    <span className="text-sm font-bold text-white">AQ</span>
                  </div>
                  <span className="ml-3 text-4xl leading-snug font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-300 to-purple-300">
                    AlignIQ
                  </span>
                </div>
              </div>
              
              {/* New Chat and Toggle buttons */}
              <div className="px-3 py-3">
                <div className="flex items-center space-x-3">
                  <NewChatButton expanded={true} onClick={onNewChat} />
                  <button 
                    onClick={toggleExpanded}
                    className="w-8 h-8 flex-shrink-0 flex items-center justify-center rounded hover:bg-white/5 transition-colors !p-0"
                    title="Collapse sidebar"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                </div>
              </div>
            </>
          ) : !isMobile && (
            // COLLAPSED SIDEBAR CONTENT - only show on desktop
            <>
              {/* Logo at the top */}
              <div className="flex-none p-3 flex justify-center">
                <div className="h-8 w-8 rounded-md bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center">
                  <span className="text-sm font-bold text-white">AQ</span>
                </div>
              </div>
              
              {/* Toggle button */}
              <div className="flex-none py-3 flex justify-center">
                <button 
                  onClick={toggleExpanded}
                  className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-white/5 transition-colors !p-0"
                  title="Expand sidebar"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </div>
              
              {/* New chat button (just the icon) */}
              <NewChatButton expanded={false} onClick={onNewChat} />
            </>
          )}
          
          {/* Conversation list - only when expanded */}
          {expanded && (
            <ConversationList
              groupedConversations={groupedConversations}
              activeConversationId={activeConversationId}
              renamingConversation={renamingConversation}
              newTitle={newTitle}
              activeDropdown={activeDropdown}
              onSelectConversation={handleSelectConversation}
              onRenameStart={handleRenameStart}
              onRenameSave={handleRenameSave}
              onRenameCancel={handleRenameCancel}
              onTitleChange={setNewTitle}
              onDeleteConversation={handleDeleteConversation}
              onDropdownToggle={setActiveDropdown}
            />
          )}
          
          {/* Bottom section - Profile menu */}
          <div className="flex-none border-t border-white/10 mt-auto">
            <div className="p-4">
              <ProfileMenu 
                user={null} 
                logout={logout} 
                sidebarExpanded={expanded} 
              />
            </div>
          </div>
          
          {/* Mobile toggle button - fixed to the edge of the screen */}
          {isMobile && !expanded && (
            <button
              className="fixed top-4 left-4 z-40 p-2 rounded-full bg-[#1c1b3b] shadow-lg border border-white/10"
              onClick={toggleExpanded}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          )}
        </div>
      </aside>
    </>
  );
};

export default Sidebar; 