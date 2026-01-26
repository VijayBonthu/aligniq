import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'react-hot-toast';

interface JiraTabProps {
  isConnected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onViewIssue?: (issueId: string) => void;
  onPanelClose: () => void;
}

interface JiraTask {
  id: string;
  key: string;
  summary: string;
  hasAttachments: boolean;
}

const JiraTab: React.FC<JiraTabProps> = ({
  isConnected,
  onConnect,
  onDisconnect,
  onViewIssue,
  onPanelClose
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [tasks, setTasks] = useState<JiraTask[]>([]);
  const [localConnected, setLocalConnected] = useState(isConnected);
  const API_URL = import.meta.env.VITE_API_URL;

  // Add event listener for auth updates
  useEffect(() => {
    // Function to handle auth updates
    const handleAuthUpdate = () => {
      console.log("Jira auth update event received");
      const jiraToken = localStorage.getItem('jira_authorization');
      
      if (jiraToken) {
        console.log("Jira token found, updating connection state");
        setLocalConnected(true);
        fetchJiraTasks(); // Immediately fetch tasks
      } else {
        console.log("No Jira token found, updating connection state");
        setLocalConnected(false);
        setTasks([]);
      }
    };

    // Listen for both storage events and our custom jiraAuthUpdate event
    window.addEventListener('storage', handleAuthUpdate);
    window.addEventListener('jiraAuthUpdate', handleAuthUpdate);
    
    // Initial check
    handleAuthUpdate();
    
    // Cleanup
    return () => {
      window.removeEventListener('storage', handleAuthUpdate);
      window.removeEventListener('jiraAuthUpdate', handleAuthUpdate);
    };
  }, []);  // Empty dependency array - only run on mount/unmount

  const fetchJiraTasks = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('token') || 
                    localStorage.getItem('regular_token') || 
                    localStorage.getItem('google_auth_token');
      const jiraToken = localStorage.getItem('jira_authorization');
      
      console.log("Fetching Jira tasks with tokens:", { appToken: token?.substring(0, 10), jiraToken: jiraToken?.substring(0, 10) });
      
      if (!token || !jiraToken) {
        setLocalConnected(false);
        throw new Error("Authentication required");
      }
      
      const response = await axios.get(`${API_URL}/jira/get_issues`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'jira_authorization': jiraToken
        }
      });
      
      console.log("Jira API response:", response.data);
      
      if (response.data && response.data.issues) {
        const jiraIssues = response.data.issues.issues.map((issue: any) => ({
          id: issue.id,
          key: issue.key,
          summary: issue.fields.summary,
          hasAttachments: issue.fields.attachment && issue.fields.attachment.length > 0
        }));
        
        setTasks(jiraIssues);
      }
    } catch (error) {
      console.error("Error fetching Jira tasks:", error);
      toast.error("Failed to load Jira tasks");
      // If we get an auth error, update local connection state
      if (error.response?.status === 401) {
        setLocalConnected(false);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDisconnect = () => {
    // Remove the token from localStorage
    localStorage.removeItem('jira_authorization');
    
    // Call the parent's disconnect handler
    onDisconnect();
    
    // Update local state immediately
    setLocalConnected(false);
    setTasks([]);
  };

  const handleConnect = () => {
    // Call the parent's connect handler
    onConnect();
  };

  const handleViewIssue = (issueId: string) => {
    if (onViewIssue) {
      onViewIssue(issueId);
    }
  };

  const handleIssueClick = (issueId: string) => {
    handleViewIssue(issueId);
    onPanelClose();
  };

  if (!localConnected) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6">
        <div className="w-16 h-16 bg-white/10 rounded-full flex items-center justify-center mb-4">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
        </div>
        <h3 className="text-xl font-semibold text-white mb-2">Connect to Jira</h3>
        <p className="text-gray-400 text-center mb-6">
          Link your Jira account to view and manage your issues directly from AlignIQ.
        </p>
        <button
          onClick={handleConnect}
          className="w-full py-2 px-4 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg text-white font-medium hover:from-blue-500 hover:to-purple-500 transition-all"
        >
          Connect Jira
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-3 border-b border-white/10 flex justify-between items-center">
        <h3 className="font-medium text-white">Your Jira Tasks</h3>
        <div className="flex space-x-2">
          <button
            onClick={fetchJiraTasks}
            className="text-gray-400 hover:text-white p-1 rounded"
            title="Refresh tasks"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <button
            onClick={handleDisconnect}
            className="text-red-400 hover:text-red-300 text-xs"
            title="Disconnect Jira"
          >
            Logout
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex justify-center items-center h-full">
            <svg className="animate-spin h-5 w-5 text-purple-500" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        ) : tasks.length > 0 ? (
          <ul className="divide-y divide-white/10">
            {tasks.map(task => (
              <li key={task.id} className="p-3 hover:bg-white/5">
                <div className="flex items-start">
                  <div className="flex-shrink-0 bg-blue-500/20 text-blue-400 rounded p-1 mr-3">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-blue-400 font-mono mb-1">{task.key}</p>
                    <h4 className="text-sm font-medium text-white truncate">{task.summary}</h4>
                    {task.hasAttachments && (
                      <div className="mt-1 flex items-center text-xs text-gray-400">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                        </svg>
                        Has attachments
                      </div>
                    )}
                  </div>
                  <button 
                    className="ml-2 text-gray-400 hover:text-white"
                    onClick={() => handleIssueClick(task.key)}
                    title="View details"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-gray-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <p className="text-gray-400 mb-4">No Jira tasks found</p>
            <button
              onClick={fetchJiraTasks}
              className="text-purple-400 hover:text-purple-300 text-sm flex items-center"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default JiraTab; 