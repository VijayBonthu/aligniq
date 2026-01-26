import React from 'react';

interface NewChatButtonProps {
  expanded: boolean;
  onClick: () => void;
}

const NewChatButton: React.FC<NewChatButtonProps> = ({ expanded, onClick }) => {
  return expanded ? (
    <div className="px-3 py-3">
      <div className="flex items-center space-x-3">
        {/* New Chat button - larger */}
        <button
          onClick={onClick}
          className="flex-1 flex items-center justify-center py-2 px-3 bg-gradient-to-r from-blue-600 to-purple-600 
            rounded-md text-white font-medium hover:from-blue-500 hover:to-purple-500 transition-all"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>
      </div>
    </div>
  ) : (
    <div className="flex-none py-3 flex justify-center">
      <button
        onClick={onClick}
        className="w-10 h-10 flex items-center justify-center bg-gradient-to-r from-blue-600 to-purple-600 
          rounded-md text-white font-medium hover:from-blue-500 hover:to-purple-500 transition-all !p-0"
        title="New Chat"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
        </svg>
      </button>
    </div>
  );
};

export default NewChatButton; 