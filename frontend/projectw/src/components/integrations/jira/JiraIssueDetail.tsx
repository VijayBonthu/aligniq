import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'react-hot-toast';

interface JiraIssueDetailProps {
  issueId: string;
  onClose: () => void;
  onAddAttachmentToAnalysis?: (file: File) => void;
}

const JiraIssueDetail: React.FC<JiraIssueDetailProps> = ({ issueId, onClose, onAddAttachmentToAnalysis }) => {
  const [issueDetails, setIssueDetails] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingAttachments, setLoadingAttachments] = useState<{[key: string]: boolean}>({});
  const API_URL = import.meta.env.VITE_API_URL;

  useEffect(() => {
    const fetchIssueDetails = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const token = localStorage.getItem('token') || 
                     localStorage.getItem('regular_token') || 
                     localStorage.getItem('google_auth_token');
        const jiraToken = localStorage.getItem('jira_authorization');
        
        if (!token || !jiraToken) {
          throw new Error("Authentication required");
        }
        
        console.log(`Fetching issue details for ${issueId}`);
        const response = await axios.get(`${API_URL}/jira/get_single_issue/${issueId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'jira_authorization': jiraToken
          }
        });
        
        console.log("Issue details response:", response.data);
        
        // Extract the issue data from the 'issues' object
        if (response.data && response.data.issues) {
          setIssueDetails(response.data.issues);
        } else {
          console.error("Unexpected API response structure:", response.data);
          setError("Invalid response format from API");
        }
      } catch (err: any) {
        console.error("Error fetching Jira issue details:", err);
        setError(err.message || "Failed to load issue details");
        toast.error("Failed to load Jira issue details");
      } finally {
        setLoading(false);
      }
    };

    if (issueId) {
      fetchIssueDetails();
    }
  }, [issueId, API_URL]);

  // Helper function to format date
  const formatDate = (dateString: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString();
  };
  
  // Helper function to safely access nested properties
  const getNestedProperty = (obj: any, path: string, defaultValue: any = '') => {
    const keys = path.split('.');
    return keys.reduce((acc, key) => (acc && acc[key] !== undefined) ? acc[key] : defaultValue, obj);
  };

  // Add a helper function to convert Atlassian Document Format (ADF) to plain text
  const convertADFToPlainText = (adf: any): string => {
    if (!adf || !adf.content) return '';
    
    let result = '';
    
    const processContent = (content: any[]) => {
      if (!content) return;
      
      content.forEach(item => {
        if (item.type === 'text') {
          result += item.text;
        } else if (item.type === 'heading') {
          result += '\n\n';
          if (item.content) {
            processContent(item.content);
          }
          result += '\n';
        } else if (item.type === 'paragraph') {
          if (item.content) {
            processContent(item.content);
          }
          result += '\n';
        } else if (item.type === 'bulletList' || item.type === 'orderedList') {
          if (item.content) {
            processContent(item.content);
          }
        } else if (item.type === 'listItem') {
          result += '• ';
          if (item.content) {
            processContent(item.content);
          }
        } else if (item.content) {
          processContent(item.content);
        }
      });
    };
    
    processContent(adf.content);
    return result;
  };

  // Add a function to check if a file is of a supported type
  const isSupportedFileType = (filename: string): boolean => {
    const supportedExtensions = ['.pdf', '.docx', '.doc', '.txt', '.pptx', '.csv'];
    const extension = filename.toLowerCase().substring(filename.lastIndexOf('.'));
    return supportedExtensions.includes(extension);
  };

  // Function to handle attachment import
  const handleImportAttachment = async (attachment: any) => {
    try {
      const attachmentId = attachment.id;
      const filename = attachment.filename;
      
      // Check file type
      if (!isSupportedFileType(filename)) {
        toast.error(`Unsupported file type. Only PDF, DOCX, DOC, TXT, PPTX, and CSV files are supported.`);
        return;
      }
      
      // Set loading state for this specific attachment
      setLoadingAttachments(prev => ({ ...prev, [attachmentId]: true }));
      
      // Get the authentication tokens
      const token = localStorage.getItem('token') || 
                   localStorage.getItem('regular_token') || 
                   localStorage.getItem('google_auth_token');
      const jiraToken = localStorage.getItem('jira_authorization');
      
      if (!token || !jiraToken) {
        throw new Error("Authentication required");
      }
      
      // Call the API to download the attachment
      const response = await axios.get(
        `${API_URL}/jira/download_attachments?issue_key=${issueDetails.key}&download_file_name=${filename}&attachment_id=${attachmentId}`, 
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'jira_authorization': jiraToken
          },
          responseType: 'blob' // Important: we need the raw file data
        }
      );
      
      // Create a File object from the response
      const fileData = new File(
        [response.data], 
        filename, 
        { type: response.data.type }
      );
      
      // Pass the file to the parent component
      if (onAddAttachmentToAnalysis) {
        onAddAttachmentToAnalysis(fileData);
        toast.success(`${filename} added to analysis queue`);
      } else {
        toast.error('Cannot add file to analysis');
      }
    } catch (err: any) {
      console.error('Error importing attachment:', err);
      toast.error(`Failed to import attachment: ${err.message || 'Unknown error'}`);
    } finally {
      // Clear loading state for this attachment
      setLoadingAttachments(prev => ({ ...prev, [attachment.id]: false }));
    }
  };

  return (
    <div className="h-full flex flex-col bg-indigo-950 p-4 overflow-auto">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold text-white flex items-center">
          <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005z" fill="#0052CC"/>
            <path d="M5.246 6.346H16.8v11.566a5.215 5.215 0 0 1-5.215 5.215 5.215 5.215 0 0 1-5.215-5.215V6.346zM16.8 0A5.215 5.215 0 0 1 22.016 5.215v2.152h2.057a5.236 5.236 0 0 1 0 10.473H12.599V6.346A6.348 6.348 0 0 1 18.947 0H16.8z" fill="#2684FF"/>
          </svg>
          Jira Issue Details
        </h2>
        <button 
          onClick={onClose} 
          className="p-1 rounded-full hover:bg-white/10 text-gray-300 hover:text-white"
          aria-label="Close"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-purple-500"></div>
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-red-500 mb-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-red-300">{error}</p>
            <button 
              onClick={() => window.location.reload()} 
              className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-md text-white"
            >
              Retry
            </button>
          </div>
        </div>
      ) : issueDetails ? (
        <div className="flex-1 overflow-auto">
          <div className="bg-indigo-900/50 rounded-lg p-4 mb-4 border border-indigo-800">
            {/* Issue Header */}
            <div className="flex items-start mb-3">
              <div className="flex-shrink-0 bg-blue-500/20 text-blue-400 rounded p-1 mr-3">
                {getNestedProperty(issueDetails, 'fields.issuetype.iconUrl') ? (
                  <img 
                    src={getNestedProperty(issueDetails, 'fields.issuetype.iconUrl')} 
                    alt={getNestedProperty(issueDetails, 'fields.issuetype.name', 'Issue')}
                    className="h-5 w-5"
                  />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                )}
              </div>
              <div>
                <h3 className="text-xl font-semibold text-white">
                  {issueDetails.key} - {getNestedProperty(issueDetails, 'fields.summary', 'No summary available')}
                </h3>
                <div className="flex flex-wrap items-center mt-1 gap-2">
                  {getNestedProperty(issueDetails, 'fields.issuetype') && (
                    <span className="inline-flex items-center bg-blue-900/30 text-blue-300 text-xs px-2 py-1 rounded">
                      {getNestedProperty(issueDetails, 'fields.issuetype.name', 'Unknown Type')}
                    </span>
                  )}
                  {getNestedProperty(issueDetails, 'fields.status') && (
                    <span className="inline-flex items-center bg-green-900/30 text-green-300 text-xs px-2 py-1 rounded">
                      {getNestedProperty(issueDetails, 'fields.status.name', 'Unknown Status')}
                    </span>
                  )}
                  {getNestedProperty(issueDetails, 'fields.priority') && (
                    <span className="inline-flex items-center bg-orange-900/30 text-orange-300 text-xs px-2 py-1 rounded flex items-center">
                      {getNestedProperty(issueDetails, 'fields.priority.iconUrl') && (
                        <img 
                          src={getNestedProperty(issueDetails, 'fields.priority.iconUrl')} 
                          alt=""
                          className="h-3 w-3 mr-1"
                        />
                      )}
                      Priority: {getNestedProperty(issueDetails, 'fields.priority.name', 'Unknown')}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Created and Updated Info */}
            <div className="flex flex-wrap gap-4 text-xs text-gray-400 mb-4">
              <div>
                <span className="font-medium">Created: </span>
                {formatDate(getNestedProperty(issueDetails, 'fields.created'))}
                {getNestedProperty(issueDetails, 'fields.creator.displayName') && (
                  <span> by {getNestedProperty(issueDetails, 'fields.creator.displayName')}</span>
                )}
              </div>
              <div>
                <span className="font-medium">Updated: </span>
                {formatDate(getNestedProperty(issueDetails, 'fields.updated'))}
              </div>
            </div>

            {/* Description */}
            {getNestedProperty(issueDetails, 'fields.description') && (
              <div className="mt-4">
                <h4 className="text-sm uppercase text-gray-400 mb-2">Description</h4>
                <div className="bg-indigo-950/70 p-3 rounded border border-indigo-800 text-gray-200 whitespace-pre-wrap">
                  {convertADFToPlainText(getNestedProperty(issueDetails, 'fields.description'))}
                </div>
              </div>
            )}

            {/* Details Grid */}
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Assignee */}
              {getNestedProperty(issueDetails, 'fields.assignee') && (
                <div>
                  <h4 className="text-sm uppercase text-gray-400 mb-2">Assignee</h4>
                  <div className="flex items-center">
                    {getNestedProperty(issueDetails, 'fields.assignee.avatarUrls.48x48') ? (
                      <img 
                        src={getNestedProperty(issueDetails, 'fields.assignee.avatarUrls.48x48')} 
                        alt={getNestedProperty(issueDetails, 'fields.assignee.displayName', '')}
                        className="w-8 h-8 rounded-full mr-2"
                      />
                    ) : (
                      <div className="w-8 h-8 bg-purple-700 rounded-full flex items-center justify-center mr-2">
                        <span className="text-white text-sm">
                          {getNestedProperty(issueDetails, 'fields.assignee.displayName', '?').charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    <span className="text-white">{getNestedProperty(issueDetails, 'fields.assignee.displayName', 'Unassigned')}</span>
                  </div>
                </div>
              )}

              {/* Reporter */}
              {getNestedProperty(issueDetails, 'fields.reporter') && (
                <div>
                  <h4 className="text-sm uppercase text-gray-400 mb-2">Reporter</h4>
                  <div className="flex items-center">
                    {getNestedProperty(issueDetails, 'fields.reporter.avatarUrls.48x48') ? (
                      <img 
                        src={getNestedProperty(issueDetails, 'fields.reporter.avatarUrls.48x48')} 
                        alt={getNestedProperty(issueDetails, 'fields.reporter.displayName', '')}
                        className="w-8 h-8 rounded-full mr-2"
                      />
                    ) : (
                      <div className="w-8 h-8 bg-blue-700 rounded-full flex items-center justify-center mr-2">
                        <span className="text-white text-sm">
                          {getNestedProperty(issueDetails, 'fields.reporter.displayName', '?').charAt(0).toUpperCase()}
                        </span>
                      </div>
                    )}
                    <span className="text-white">{getNestedProperty(issueDetails, 'fields.reporter.displayName', 'Unknown')}</span>
                  </div>
                </div>
              )}

              {/* Additional fields like components, labels, etc. */}
              {getNestedProperty(issueDetails, 'fields.components', []).length > 0 && (
                <div>
                  <h4 className="text-sm uppercase text-gray-400 mb-2">Components</h4>
                  <div className="flex flex-wrap gap-1">
                    {getNestedProperty(issueDetails, 'fields.components', []).map((component: any, index: number) => (
                      <span key={index} className="bg-purple-900/30 text-purple-300 text-xs px-2 py-1 rounded">
                        {component.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Labels */}
              {getNestedProperty(issueDetails, 'fields.labels', []).length > 0 && (
                <div>
                  <h4 className="text-sm uppercase text-gray-400 mb-2">Labels</h4>
                  <div className="flex flex-wrap gap-1">
                    {getNestedProperty(issueDetails, 'fields.labels', []).map((label: string, index: number) => (
                      <span key={index} className="bg-indigo-900/30 text-indigo-300 text-xs px-2 py-1 rounded">
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Attachments - Modified with import button */}
            {getNestedProperty(issueDetails, 'fields.attachment', []).length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm uppercase text-gray-400 mb-2">
                  Attachments ({getNestedProperty(issueDetails, 'fields.attachment', []).length})
                </h4>
                <ul className="space-y-2">
                  {getNestedProperty(issueDetails, 'fields.attachment', []).map((attachment: any, index: number) => (
                    <li key={index} className="bg-indigo-950/70 p-2 rounded border border-indigo-800">
                      <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-2">
                        <a 
                          href={attachment.content || attachment.self} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="flex items-center text-blue-400 hover:text-blue-300 min-w-0"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 flex-shrink-0 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                          </svg>
                          <span className="truncate">{attachment.filename}</span>
                          <span className="ml-2 text-xs text-gray-400 flex-shrink-0">
                            ({Math.round((attachment.size || 0) / 1024)} KB)
                          </span>
                        </a>
                        
                        {/* Show import button only for supported file types */}
                        {isSupportedFileType(attachment.filename) && onAddAttachmentToAnalysis && (
                          <button
                            className="flex items-center bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded px-2 py-1 transition-colors self-start md:self-center flex-shrink-0"
                            onClick={() => handleImportAttachment(attachment)}
                            disabled={loadingAttachments[attachment.id]}
                            title="Import this file for analysis"
                          >
                            {loadingAttachments[attachment.id] ? (
                              <svg className="animate-spin h-3 w-3 mr-1" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                            ) : (
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 13h6m-3-3v6" />
                              </svg>
                            )}
                            Use for Analysis
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Comments */}
            {getNestedProperty(issueDetails, 'fields.comment.comments', []).length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm uppercase text-gray-400 mb-2">
                  Comments ({getNestedProperty(issueDetails, 'fields.comment.comments', []).length})
                </h4>
                <div className="space-y-3">
                  {getNestedProperty(issueDetails, 'fields.comment.comments', []).map((comment: any, index: number) => (
                    <div key={index} className="bg-indigo-950/70 p-3 rounded border border-indigo-800">
                      <div className="flex items-center mb-2">
                        {getNestedProperty(comment, 'author.avatarUrls.24x24') ? (
                          <img 
                            src={getNestedProperty(comment, 'author.avatarUrls.24x24')} 
                            alt={getNestedProperty(comment, 'author.displayName', '')}
                            className="w-5 h-5 rounded-full mr-2"
                          />
                        ) : (
                          <div className="w-5 h-5 bg-purple-700 rounded-full flex items-center justify-center mr-2">
                            <span className="text-white text-xs">
                              {getNestedProperty(comment, 'author.displayName', '?').charAt(0).toUpperCase()}
                            </span>
                          </div>
                        )}
                        <span className="text-sm text-gray-300">{getNestedProperty(comment, 'author.displayName', 'Unknown')}</span>
                        <span className="text-xs text-gray-500 ml-2">
                          {formatDate(getNestedProperty(comment, 'created', ''))}
                        </span>
                      </div>
                      <div className="text-gray-200 whitespace-pre-wrap">
                        {typeof getNestedProperty(comment, 'body') === 'string'
                          ? getNestedProperty(comment, 'body', 'No comment text')
                          : convertADFToPlainText(getNestedProperty(comment, 'body', {}))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-400">
            <p>No issue details available</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default JiraIssueDetail; 