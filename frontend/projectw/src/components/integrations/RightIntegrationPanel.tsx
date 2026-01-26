import React from 'react';
import JiraTab from './jira/JiraTab';

type IntegrationType = 'jira' | 'github' | 'azure';

interface RightIntegrationPanelProps {
  integrationType: IntegrationType;
  onClose: () => void;
  jiraToken: string | null;
  onJiraConnect: () => void;
  onJiraDisconnect: () => void;
}

const RightIntegrationPanel: React.FC<RightIntegrationPanelProps> = ({
  integrationType,
  onClose,
  jiraToken,
  onJiraConnect,
  onJiraDisconnect
}) => {
  return (
    <div className="fixed inset-y-0 right-0 w-80 bg-[#1a1742] shadow-xl z-30 border-l border-white/10 flex flex-col animate-slide-in-right">
      <div className="flex-none p-3 border-b border-white/10 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">
          {integrationType === 'jira' && 'Jira Integration'}
          {integrationType === 'github' && 'GitHub Integration'}
          {integrationType === 'azure' && 'Azure DevOps Integration'}
        </h2>
        <button 
          onClick={onClose}
          className="text-gray-400 hover:text-white p-1 rounded"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        {integrationType === 'jira' && (
          <JiraTab 
            isConnected={!!jiraToken}
            onConnect={onJiraConnect}
            onDisconnect={onJiraDisconnect}
          />
        )}
        {integrationType === 'github' && (
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
            </svg>
            <h3 className="text-xl font-semibold text-white mb-3">GitHub Integration</h3>
            <p className="text-gray-400 mb-6">GitHub integration coming soon!</p>
          </div>
        )}
        {integrationType === 'azure' && (
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-gray-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <h3 className="text-xl font-semibold text-white mb-3">Azure DevOps Integration</h3>
            <p className="text-gray-400 mb-6">Azure DevOps integration coming soon!</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default RightIntegrationPanel; 