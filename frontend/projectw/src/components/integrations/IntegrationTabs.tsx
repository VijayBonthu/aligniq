import React from 'react';

type TabType = 'jira' | 'github' | 'azure';

interface IntegrationTabsProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  jiraConnected: boolean;
}

const IntegrationTabs: React.FC<IntegrationTabsProps> = ({
  activeTab,
  onTabChange,
  jiraConnected
}) => {
  return (
    <div className="flex border-b border-white/10">
      <TabButton 
        isActive={activeTab === 'jira'}
        onClick={() => onTabChange('jira')}
        icon={
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 18a6 6 0 000-12v12z" />
            <path d="M19 6l-7 6 7 6" />
          </svg>
        }
        label="Jira"
        connected={jiraConnected}
      />
      <TabButton 
        isActive={activeTab === 'github'}
        onClick={() => onTabChange('github')}
        icon={
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
          </svg>
        }
        label="GitHub"
        connected={false}
      />
      <TabButton 
        isActive={activeTab === 'azure'}
        onClick={() => onTabChange('azure')}
        icon={
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
          </svg>
        }
        label="Azure"
        connected={false}
      />
    </div>
  );
};

interface TabButtonProps {
  isActive: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  connected: boolean;
}

const TabButton: React.FC<TabButtonProps> = ({
  isActive,
  onClick,
  icon,
  label,
  connected
}) => {
  return (
    <button
      className={`flex items-center px-4 py-2 border-b-2 flex-1 ${
        isActive 
          ? 'border-purple-500 text-white' 
          : 'border-transparent text-gray-400 hover:text-gray-300'
      }`}
      onClick={onClick}
    >
      <span className="mr-2">{icon}</span>
      <span>{label}</span>
      {connected && (
        <span className="ml-2 flex-shrink-0 w-2 h-2 rounded-full bg-green-500"></span>
      )}
    </button>
  );
};

export default IntegrationTabs; 