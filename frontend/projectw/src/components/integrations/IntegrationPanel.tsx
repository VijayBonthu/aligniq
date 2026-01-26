import React, { useState, useEffect } from 'react';
import JiraTab from './jira/JiraTab';
import IntegrationTabs from './IntegrationTabs';

type TabType = 'jira' | 'github' | 'azure';

interface IntegrationPanelProps {
  isExpanded: boolean;
  onToggle: () => void;
  jiraToken: string | null;
  onJiraConnect: () => void;
  onJiraDisconnect: () => void;
  initialActiveTab?: TabType;
  onViewJiraIssue?: (issueId: string) => void;
}

const IntegrationPanel: React.FC<IntegrationPanelProps> = ({
  isExpanded,
  onToggle,
  jiraToken,
  onJiraConnect,
  onJiraDisconnect,
  initialActiveTab = 'jira',
  onViewJiraIssue
}) => {
  const [activeTab, setActiveTab] = useState<TabType>(initialActiveTab);
  
  useEffect(() => {
    if (initialActiveTab) {
      setActiveTab(initialActiveTab);
    }
  }, [initialActiveTab]);

  if (!isExpanded) {
    return null;
  }

  return (
    <div className="fixed right-0 top-0 bottom-0 bg-[#1a1742] border-l border-white/10 w-80 flex flex-col h-full shadow-xl z-30 animate-slide-in-right">
      <div className="flex-none p-3 border-b border-white/10 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Integrations</h2>
        <button 
          onClick={onToggle}
          className="text-gray-400 hover:text-white p-1 rounded"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
      
      <IntegrationTabs 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
        jiraConnected={!!jiraToken}
      />
      
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'jira' && (
          <JiraTab 
            isConnected={!!jiraToken}
            onConnect={onJiraConnect}
            onDisconnect={onJiraDisconnect}
            onViewIssue={onViewJiraIssue}
            onPanelClose={onToggle}
          />
        )}
        {activeTab === 'github' && (
          <div className="p-4 text-gray-400 text-center">
            <p>GitHub integration coming soon</p>
          </div>
        )}
        {activeTab === 'azure' && (
          <div className="p-4 text-gray-400 text-center">
            <p>Azure DevOps integration coming soon</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default IntegrationPanel; 