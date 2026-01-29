import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { toast } from 'react-hot-toast';
import * as marked from 'marked'; // Change to namespace import
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
// Import the Sidebar component
import Sidebar from '../components/sidebar/Sidebar';
import RightSidebar from '../components/integrations/RightSidebar';
import JiraIssueDetail from '../components/integrations/jira/JiraIssueDetail';

const API_URL = import.meta.env.VITE_API_URL;

// Define types for our data structures
interface Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// New unified question interface matching backend
interface PresalesQuestion {
  question_id: string;
  presales_id: string;
  question_type: 'p1_blocker' | 'kickstart';
  question_number: string;  // 'P1-1', 'Q1', etc.
  display_order: number;
  area_or_category: string;
  title: string;
  description: string;  // why_it_matters or why_critical
  impact_description?: string;  // impact_if_unknown
  question_text: string;
  answer?: string;
  answer_quality?: 'good' | 'vague' | 'contradicting';
  answer_feedback?: string;
  answered_at?: string;
  status: 'pending' | 'answered' | 'invalid' | 'needs_review';
  invalidated_reason?: string;
  invalidated_at?: string;
}

// Readiness analysis result
interface ReadinessResult {
  score: number;
  status: 'not_analyzed' | 'needs_more_info' | 'ready_with_assumptions' | 'ready';
  summary?: string;
  p1_answered?: number;
  p1_total?: number;
  kickstart_answered?: number;
  kickstart_total?: number;
}

interface Contradiction {
  question_ids: string[];
  description: string;
  explanation: string;
  suggested_resolution: string;
}

interface VagueAnswer {
  question_id: string;
  current_answer: string;
  issue: string;
  expected_format: string;
  impact: string;
}

interface Assumption {
  for_question_id: string;
  assumption: string;
  basis: string;
  risk_level: 'low' | 'medium' | 'high';
  impact_if_wrong: string;
}

// Legacy interfaces for backward compatibility
interface KickstartQuestion {
  category: string;
  question: string;
  why_critical: string;
  impact_if_unknown: string;
  answer?: string;
}

interface P1Blocker {
  area: string;
  blocker: string;
  why_it_matters: string;
  question: string;
  answer?: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  messages: Message[];
  document_id: string;
  chat_history_id: string | null;
  modified_at: string;
  analysis_mode?: 'presales' | 'full';
  presales_id?: string;
  // New unified questions from backend
  questions?: PresalesQuestion[];
  // Legacy fields for backward compatibility
  p1_blockers?: P1Blocker[];
  kickstart_questions?: KickstartQuestion[];
  blind_spots?: any;
  // Readiness tracking
  readiness?: ReadinessResult;
  contradictions?: Contradiction[];
  vague_answers?: VagueAnswer[];
  assumptions?: Assumption[];
}

interface Recommendation {
  tech_stack: string[];
  developers_required: {
    role: string;
    count: number;
    skills: string[];
  }[];
  ambiguities: string[];
  summary: string;
}

// Enhanced types for conversation data
interface ConversationMetadata {
  chat_history_id: string;
  title: string;
  modified_at: string;
  document_id?: string;
}

interface GroupedConversations {
  today: ConversationMetadata[];
  yesterday: ConversationMetadata[];
  lastWeek: ConversationMetadata[];
  older: ConversationMetadata[];
}

const Dashboard: React.FC = () => {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [fileProgresses, setFileProgresses] = useState<{[key: string]: number}>({});
  const [isUploading, setIsUploading] = useState(false);
  const [totalProgress, setTotalProgress] = useState(0);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [message, setMessage] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [error, setError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [groupedConversations, setGroupedConversations] = useState<GroupedConversations>({
    today: [],
    yesterday: [],
    lastWeek: [],
    older: []
  });
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null);
  const [renamingConversation, setRenamingConversation] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [showUploadUI, setShowUploadUI] = useState(true);
  // Near the top of the Dashboard component - add new state for selected messages
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  // First, add this state near your other state declarations
  const [showIntegrationModal, setShowIntegrationModal] = useState(false);
  const [showIntegrationPanel, setShowIntegrationPanel] = useState(false);
  const [integrationDropdownOpen, setIntegrationDropdownOpen] = useState(false);
  const [integrationTab, setIntegrationTab] = useState<'jira' | 'github' | 'azure'>('jira');
  const [isSplitView, setIsSplitView] = useState(false);
  // Presales-specific state
  const [showKickstartPanel, setShowKickstartPanel] = useState(false);
  const [kickstartAnswers, setKickstartAnswers] = useState<Record<string, string>>({});
  const [isSavingAnswers, setIsSavingAnswers] = useState(false);
  const [isPresalesChatting, setIsPresalesChatting] = useState(false);
  const [selectedJiraIssue, setSelectedJiraIssue] = useState<string | null>(null);
  // Readiness analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showReadinessModal, setShowReadinessModal] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{
    readiness: ReadinessResult;
    contradictions: Contradiction[];
    vague_answers: VagueAnswer[];
    assumptions: Assumption[];
    recommendations: string[];
    can_generate_report: boolean;
  } | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  // Add a debounce tracking variable
  const refreshInProgress = useRef(false);
  const refreshTimeout = useRef<number | null>(null);
  // Add flag to track if data has actually changed 
  const dataChanged = useRef(false);

  // Check authentication on component mount
  useEffect(() => {
    if (!isAuthenticated) {
      navigate('/login');
    } else {
      // Fetch existing conversations only once at mount
      console.log("Initial conversations fetch on component mount");
      fetchConversations();
      
      // We don't need to refresh on visibility change - removing for performance
      // Only refresh when actual data changes occur (uploads, chat interactions)
    }
  }, [isAuthenticated, navigate]);

  // Simplify the resize effect
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    // Set initial state
    handleResize();
    
    // Add event listener
    window.addEventListener('resize', handleResize);
    
    // Cleanup
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // First, improve the scrollToBottom function to be more reliable
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      // Use setTimeout to ensure this happens after DOM updates
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
    }
  };

  // Make sure we're also scrolling when typing indicators appear
  useEffect(() => {
    // This will trigger scrolling whenever messages change, including typing indicators
    if (activeConversation?.messages?.some(msg => msg.content === '...')) {
      scrollToBottom();
    }
  }, [activeConversation?.messages]);

  // Add this as well to ensure scrolling happens after state updates
  useEffect(() => {
    if (isSendingMessage) {
      scrollToBottom();
    }
  }, [isSendingMessage]);

  // Fetch user's conversations with full content
  const fetchConversations = async () => {
    try {
      const timestamp = new Date().getTime();
      console.log(`Starting fetchConversations at timestamp: ${timestamp}`);
      
      // Get the token for authentication
      const token = localStorage.getItem('token') || 
                  localStorage.getItem('regular_token') || 
                  localStorage.getItem('google_auth_token');
      
      if (!token) {
        console.error("No token found");
        return;
      }
      
      // Set the authorization header explicitly and add cache-busting parameter
      const response = await axios.get(`${API_URL}/chat?_t=${timestamp}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      console.log(`Received conversations data at timestamp: ${timestamp}`);
      
      if (response.data && response.data.user_details) {
        // Sort conversations by modified_at descending (newest first)
        const sortedConversations = [...response.data.user_details].sort((a, b) => 
          new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
        );
        
        // Group conversations by date
        const grouped = groupConversationsByDate(sortedConversations);
        
        // Update state with the new conversations
        setGroupedConversations(grouped);
        
        // Also update the old conversations array for the collapsed sidebar
        const conversationsArray = sortedConversations.slice(0, 5).map(conv => ({
          id: conv.chat_history_id,
          title: conv.title,
          created_at: conv.modified_at,
          messages: [],
          document_id: conv.document_id || '',
          chat_history_id: conv.chat_history_id,
          modified_at: conv.modified_at
        }));
        
        setConversations(conversationsArray);
        
        console.log(`Updated conversation states at timestamp: ${timestamp}`);
      }
    } catch (error) {
      console.error('Error fetching conversations:', error);
    }
  };

  // Helper function to group conversations by time period
  const groupConversationsByDate = (conversations: ConversationMetadata[]): GroupedConversations => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const lastWeekStart = new Date(today);
    lastWeekStart.setDate(lastWeekStart.getDate() - 7);
    
    return {
      today: conversations.filter(conv => new Date(conv.modified_at) >= today),
      yesterday: conversations.filter(conv => {
        const date = new Date(conv.modified_at);
        return date >= yesterday && date < today;
      }),
      lastWeek: conversations.filter(conv => {
        const date = new Date(conv.modified_at);
        return date >= lastWeekStart && date < yesterday;
      }),
      older: conversations.filter(conv => new Date(conv.modified_at) < lastWeekStart)
    };
  };

  // Add this function to remove a file from the files array
  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Add helper function to format file sizes
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' bytes';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  };

  // Create simple FileIcon component based on file type
  const FileIcon = ({ type }: { type: string }) => {
    // Choose icon based on file type
    let iconPath;
    
    if (type.includes('pdf')) {
      iconPath = (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      );
    } else if (type.includes('powerpoint') || type.includes('presentation')) {
      iconPath = (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 13v-1m4 1v-3m4 3V8M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
      );
    } else if (type.includes('csv')) {
      iconPath = (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      );
      } else {
      // Default document icon
      iconPath = (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      );
    }
    
    return (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        {iconPath}
      </svg>
    );
  };

  // Create TrashIcon component
  const TrashIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );

  // Update handleFileChange to properly validate files
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      
      // Validate files (size and type)
      const validFiles = newFiles.filter(file => {
        // Check file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
          setError(`File "${file.name}" exceeds the 10MB limit.`);
          return false;
        }
        
        // Check file type
        const fileType = file.type;
        const fileExtension = file.name.split('.').pop()?.toLowerCase();
        
        const isValidType = 
          fileType.includes('pdf') || 
          fileType.includes('powerpoint') || 
          fileType.includes('text/plain') || 
          fileType.includes('text/csv') ||
          fileExtension === 'pdf' ||
          fileExtension === 'ppt' ||
          fileExtension === 'pptx' ||
          fileExtension === 'txt' ||
          fileExtension === 'csv';
          
        if (!isValidType) {
          setError(`File "${file.name}" has an unsupported format.`);
          return false;
        }
        
        return true;
      });
      
      setFiles(prev => [...prev, ...validFiles]);
    }
  };

  // Replace instances of this problematic code:
  // localStorage.setItem('user_id', userId);

  // With this safer version that handles the null case:
  const decodeTokenAndSaveUserId = async (token: string) => {
    try {
      const response = await axios.get(`${API_URL}/decode_token/${token}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.data && response.data.id) {
        const userId = response.data.id;
        // Store for future use with null check
        if (userId) {
          localStorage.setItem('user_id', userId);
        }
        return userId;
      }
    } catch (error) {
      console.error('Error decoding token:', error);
      setError('Failed to authenticate user');
    }
    return null;
  };

  // Handle file upload for document analysis
  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select a file to upload');
      return;
    }

    setIsUploading(true);
    setTotalProgress(0);
    setError('');

      const formData = new FormData();
    files.forEach(file => formData.append('file', file));

    try {
      const token = localStorage.getItem('token') || localStorage.getItem('regular_token') || localStorage.getItem('google_auth_token');
      
      if (!token) {
        throw new Error('No authentication token found');
      }
      
      // Get userId from localStorage instead of making an API call
      let userId = localStorage.getItem('user_id');
      
      // Only decode token if userId is not in localStorage
      if (!userId) {
        userId = await decodeTokenAndSaveUserId(token);
        if (!userId) {
          throw new Error('Could not get user ID');
        }
      }
      
      // Upload the files and get initial analysis
      const uploadResponse = await axios.post(`${API_URL}/upload`, formData, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1));
          setTotalProgress(percentCompleted);
        }
      });
      
      setIsProcessing(true);

      // Get document_id, chat_history_id and other data from the upload response
      const documentId = uploadResponse.data.document_id;
      const analysisMode = uploadResponse.data.analysis_mode || 'full';
      const isPresales = analysisMode === 'presales';
      const chatHistoryId = isPresales ? null : (uploadResponse.data.chat_history_id || documentId);
      const chatTitle = uploadResponse.data.title || `Analysis of ${files[0].name}`;
      const presalesId = uploadResponse.data.presales_id;

      // Create initial assistant message using the actual API response message
      const initialMessage: Message = {
        role: 'assistant',
        content: uploadResponse.data.message, // Use the actual message from the API
        timestamp: new Date().toISOString(),
        selected: true  // Initial message is selected by default
      };

      // Extract P1 blockers and kickstart questions from presales response
      let p1Blockers: P1Blocker[] = [];
      let kickstartQuestions: KickstartQuestion[] = [];
      if (isPresales) {
        // Extract P1 blockers
        if (uploadResponse.data.p1_blockers) {
          p1Blockers = uploadResponse.data.p1_blockers;
        }
        // Extract kickstart questions
        if (uploadResponse.data.kickstart_questions) {
          kickstartQuestions = uploadResponse.data.kickstart_questions;
        } else if (uploadResponse.data.blind_spots?.critical_unknowns) {
          kickstartQuestions = uploadResponse.data.blind_spots.critical_unknowns;
        }
      }

      // Create a new conversation with the document info from the API response
      const newConversation: Conversation = {
        id: isPresales ? presalesId : chatHistoryId,  // Use presales_id or chat_history_id as the ID
        title: chatTitle,
        created_at: new Date().toISOString(),
        messages: [initialMessage],
        document_id: documentId || '',
        chat_history_id: chatHistoryId,  // null for presales mode
        modified_at: new Date().toISOString(),
        analysis_mode: analysisMode,
        presales_id: presalesId,
        p1_blockers: p1Blockers,
        kickstart_questions: kickstartQuestions,
        blind_spots: uploadResponse.data.blind_spots
      };

      setActiveConversation(newConversation);

      // Reset kickstart answers when new presales analysis starts
      if (isPresales) {
        setKickstartAnswers({});
        setShowKickstartPanel(true);  // Auto-show the panel for presales
      }

      // Only refresh conversations list for full analysis (presales doesn't create chat history)
      if (!isPresales) {
        fetchConversations();
      }
      
      // Reset file state
      setFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error: any) {
      console.error('Upload error:', error);
      setError(error.response?.data?.detail || 'Failed to upload and process documents');
    } finally {
      setIsUploading(false);
      setIsProcessing(false);
    }
  };

  // Add this function
  const autoResizeTextarea = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  };

  // Update the message change handler
  const handleMessageChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    setTimeout(autoResizeTextarea, 0);
  };

  // Improved selectConversation function with proper loading and parsing
  const selectConversation = async (chatHistoryId: string) => {
    try {
      setIsLoadingConversation(true);
      setError('');
      
      // Get the authentication token
      const token = localStorage.getItem('token') || 
                   localStorage.getItem('regular_token') || 
                   localStorage.getItem('google_auth_token');
      
      if (!token) {
        throw new Error("No authentication token found");
      }
      
      // Fetch the specific conversation
      const response = await axios.get(`${API_URL}/chat/${chatHistoryId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.data && response.data.user_details) {
        const details = response.data.user_details;
        
        // Parse the messages array from the string
        let messages: Message[] = [];

        try {
          // Handle message parsing with error checking
          if (typeof details.message === 'string') {
            messages = JSON.parse(details.message);
          } else if (Array.isArray(details.message)) {
            messages = details.message;
            } else {
            console.error("Unexpected message format:", details.message);
            messages = [];
          }
        } catch (e) {
          console.error("Error parsing messages:", e);
          messages = [];
        }

        // Add IDs to messages and preserve selection state from backend
        const messagesWithIds = messages.map((msg, index) => ({
          ...msg,
          id: msg.id || `msg-${index}-${Date.now()}`,
          selected: msg.selected ?? true  // Use backend's selected state, default to true if not present
        }));

        // Set up selectedMessageIds based on the selected field from backend
        const selectedIds = messagesWithIds
          .filter(msg => msg.selected)
          .map(msg => msg.id!)
          .filter((id): id is string => id !== undefined);

        setSelectedMessageIds(selectedIds);

        // Create a conversation object with the full data
        const conversation: Conversation = {
          id: details.chat_history_id,
          title: details.title,
          created_at: details.modified_at,
          messages: messagesWithIds,
          document_id: details.document_id || '',
          chat_history_id: details.chat_history_id,
          modified_at: details.modified_at
        };

        setActiveConversation(conversation);
        
        // Auto-close sidebar on mobile
        if (isMobile && sidebarExpanded) {
          setSidebarExpanded(false);
        }
            } else {
        throw new Error("Invalid response format");
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
      setError('Failed to load conversation');
    } finally {
      setIsLoadingConversation(false);
    }
  };

  // Update handleSendMessage function to mark new messages and responses as selected by default
  const handleSendMessage = async () => {
    if (!message.trim() || isSendingMessage || !activeConversation) return;
    
    setIsSendingMessage(true);
    
    try {
      // Get authentication tokens
      const token = localStorage.getItem('token') || 
                    localStorage.getItem('regular_token') || 
                    localStorage.getItem('google_auth_token');
      const userId = localStorage.getItem('user_id');
      
      if (!token || !userId) {
        toast.error("Authentication token or user ID not found. Please log in again.");
        return;
      }
      
      // Create a temporary message for immediate UI update
      const tempMsgId = `temp-${Date.now()}`;
      const tempMsg: Message = {
        id: tempMsgId,
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
        selected: true  // New user messages are always selected
      };
      
      // Add the new user message ID to selected messages
      setSelectedMessageIds(prev => [...prev, tempMsgId]);
      
      // Make a copy of the active conversation with the new message
      const updatedConversation = {
        ...activeConversation,
        messages: [...activeConversation.messages, tempMsg]
      };
      
      // Update UI immediately
      setActiveConversation(updatedConversation);
      setMessage('');
      
      // Add a placeholder for the assistant's response
      const assistantPlaceholder: Message = {
        role: 'assistant',
        content: '...',
        timestamp: new Date().toISOString(),
        selected: true  // Placeholder is selected by default
      };
      
      // Show typing indicator
      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: [...prev.messages, assistantPlaceholder]
        };
      });
      
      // Prepare ALL messages with selection state (use msg.selected field if available)
      const allMessagesWithSelection = activeConversation.messages.map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
        // Use msg.selected if it exists, otherwise check selectedMessageIds
        selected: msg.selected !== undefined ? msg.selected : (msg.id ? selectedMessageIds.includes(msg.id) : true)
      }));

      // Add the new user message (selected by default)
      const userMessageForApi = {
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
        selected: true  // New user messages are always selected by default
      };

      // STEP 1: Call the chat-with-doc endpoint with ALL messages (with selection state)
      const response = await axios.post(
        `${API_URL}/chat-with-doc`,
        {
          chat_history_id: updatedConversation.chat_history_id || updatedConversation.id,  // Use actual chat_history_id
          user_id: userId,
          document_id: updatedConversation.document_id || '',
          message: [...allMessagesWithSelection, userMessageForApi],  // ALL messages with selected field
          title: updatedConversation.title
        },
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );
      
      // Process the response
      if (response.data) {
        // Create assistant message from the response
        const assistantMsgId = `assistant-${Date.now()}`;
        const assistantMessage: Message = {
          id: assistantMsgId,
          role: 'assistant',
          content: response.data.message || "No response from the server",
          timestamp: new Date().toISOString(),
          selected: true  // New assistant messages are selected by default
        };

        // Add the assistant response ID to selected messages
        setSelectedMessageIds(prev => [...prev, assistantMsgId]);

        // Update conversation with the final message
        const finalMessages = updatedConversation.messages
          .filter(msg => msg.role !== 'assistant' || msg.content !== '...') // Remove placeholder
          .concat([assistantMessage]);

        setActiveConversation({
          ...updatedConversation,
          messages: finalMessages
        });

        // STEP 2: Save the updated conversation to the /chat endpoint with ALL messages
        // Clean messages for API (remove IDs but keep selected state)
        const cleanMessages = finalMessages.map(msg => ({
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
          // Use msg.selected if available, otherwise default to true
          selected: msg.selected !== undefined ? msg.selected : true
        }));
        
        await axios.post(
          `${API_URL}/chat`,
          {
            user_id: userId,
            document_id: updatedConversation.document_id || '',
            message: cleanMessages, // Send ALL messages in the correct format
            title: updatedConversation.title || 'Chat Session'
          },
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        );
        
        // Refresh conversation list
        fetchConversations();
        
        // Mark that data has changed
        dataChanged.current = true;
        
        // Scroll to bottom
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      toast.error('Failed to send message');
      
      // Remove loading indicator on error
      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: prev.messages.filter(msg => msg.content !== '...')
        };
      });
    } finally {
      setIsSendingMessage(false);
    }
  };

  // Start a new conversation
  const startNewConversation = () => {
    setActiveConversation(null);
    setRecommendation(null);
    setFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  // Simple toggle function - just expands for now
  const toggleSidebar = () => {
    setSidebarExpanded(!sidebarExpanded);
  };

  // Update the handleLogout function in Dashboard component
  const handleLogout = () => {
    // First, clear any Jira tokens
    localStorage.removeItem('jira_authorization');
    
    // Then perform the normal logout
    logout();
    navigate('/login');
  };

  // Updated deleteConversation function to properly handle last conversation deletion
  const deleteConversation = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent triggering conversation selection
    
    if (window.confirm('Are you sure you want to delete this conversation?')) {
      try {
        const token = localStorage.getItem('token') || 
                     localStorage.getItem('regular_token') || 
                     localStorage.getItem('google_auth_token');
                     
        if (!token) {
          console.error("No token found");
        return;
      }
      
        // Delete the conversation from the backend
        await axios.delete(`${API_URL}/chat/${chatId}`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        // Important: Reset active conversation FIRST if it's the one being deleted
        if (activeConversation?.id === chatId) {
          setActiveConversation(null);
        }
        
        // Update local conversation state to immediately reflect deletion
        setGroupedConversations(prevState => {
          const newState = {...prevState};
          
          // Remove the deleted conversation from each period
          Object.keys(newState).forEach(period => {
            if (period in newState) {
              newState[period as keyof GroupedConversations] = newState[period as keyof GroupedConversations].filter(
                conv => conv.chat_history_id !== chatId
              );
            }
          });
          
          return newState;
        });
        
        // Also update the original conversations array for consistency
        setConversations(prev => prev.filter(conv => conv.id !== chatId));
        
        // Close any open dropdown
        setActiveDropdown(null);
        
        // Mark data as changed
        dataChanged.current = true;
        
        // Fetch fresh conversations to ensure UI is in sync with backend
        fetchConversations();
        
    } catch (error) {
        console.error('Error deleting conversation:', error);
        setError('Failed to delete conversation');
        
        // If we get a 404, the conversation is already gone from backend
        // So we should still clean up the UI
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          if (activeConversation?.id === chatId) {
            setActiveConversation(null);
          }
          
          setGroupedConversations(prevState => {
            const newState = {...prevState};
            
            Object.keys(newState).forEach(period => {
              if (period in newState) {
                newState[period as keyof GroupedConversations] = newState[period as keyof GroupedConversations].filter(
                  conv => conv.chat_history_id !== chatId
                );
              }
            });
            
            return newState;
          });
          
          setConversations(prev => prev.filter(conv => conv.id !== chatId));
          setActiveDropdown(null);
        }
      }
    }
  };

  // Add function to rename conversation
  const renameConversation = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent triggering conversation selection
    
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

  // Function to handle saving the new title - CORRECTED VERSION
  const saveNewTitle = async (chatId: string, e: React.FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!newTitle.trim()) return;
    
    try {
      const token = localStorage.getItem('token') || 
                   localStorage.getItem('regular_token') || 
                   localStorage.getItem('google_auth_token');
                   
      if (!token) {
        console.error("No token found");
        return;
      }

      // First fetch the complete conversation details
      const chatResponse = await axios.get(`${API_URL}/chat/${chatId}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!chatResponse.data || !chatResponse.data.user_details) {
        throw new Error("Invalid response when fetching conversation details");
      }
      
      const details = chatResponse.data.user_details;
      
      // Parse the messages array from the string
      let messages;
      try {
        if (typeof details.message === 'string') {
          messages = JSON.parse(details.message);
        } else if (Array.isArray(details.message)) {
          messages = details.message;
        } else {
          console.error("Unexpected message format:", details.message);
          messages = [];
        }
      } catch (e) {
        console.error("Error parsing messages:", e);
        messages = [];
      }
      
      // Get user ID from localStorage
      const userId = localStorage.getItem('user_id');
      if (!userId) {
        throw new Error("User ID not found in localStorage");
      }
      
      // Update the conversation with POST
      await axios.post(`${API_URL}/chat`, 
        {
          chat_history_id: chatId,
          user_id: userId,
          document_id: details.document_id || "",
          message: messages,
          title: newTitle.trim()
        },
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      
      // Mark data as changed
      dataChanged.current = true;
      
      // Refresh conversations to get updated title
      fetchConversations();
      
      // Clear renaming state
      setRenamingConversation(null);
      setNewTitle('');
      
    } catch (error) {
      console.error('Error renaming conversation:', error);
      setError('Failed to rename conversation');
    }
  };

  // Cancel renaming
  const cancelRenaming = (e: React.MouseEvent) => {
    e.stopPropagation();
    setRenamingConversation(null);
    setNewTitle('');
  };

  // Add these event handlers to prevent browser default behavior for drag and drop
  const handleDragOver = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      // Use the existing file change handler with the dropped files
      const fileChangeEvent = {
        target: {
          files: e.dataTransfer.files
        }
      } as React.ChangeEvent<HTMLInputElement>;
      
      handleFileChange(fileChangeEvent);
    }
  };

  // Function to copy message content
  const handleCopyMessage = (message: Message) => {
    navigator.clipboard.writeText(message.content)
      .then(() => {
        // Show success toast
        toast.success('Message copied to clipboard');
      })
      .catch(err => {
        console.error('Failed to copy: ', err);
        toast.error('Failed to copy message');
      });
  };

  // Function to download message as PDF - with improved markdown formatting support
  const handleDownloadPDF = async (message: Message) => {
    try {
      // Show loading toast
      const loadingToast = toast.loading("Generating PDF...");
      
      // Initialize PDF with A4 format
      const pdf = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });
      
      // Set basic information
      const pageWidth = 210; // A4 width in mm
      const pageHeight = 297; // A4 height in mm
      const margin = 20; // Margins in mm
      const contentWidth = pageWidth - (margin * 2); // Available width for content
      
      // Add header
      pdf.setFontSize(10);
      pdf.setTextColor(150, 150, 150);
      pdf.text(`Generated on ${new Date().toLocaleDateString()}`, pageWidth - margin - 50, margin);
      pdf.line(margin, margin + 5, pageWidth - margin, margin + 5);
      
      // Start position after header
      let yPosition = margin + 15;
      const normalLineHeight = 7; // Normal line height in mm
      
      // Add title
      pdf.setFontSize(16);
      pdf.setTextColor(60, 60, 60);
      pdf.setFont('helvetica', 'bold');
      pdf.text('AlignIQ Analysis', margin, yPosition);
      yPosition += normalLineHeight * 2;
      
      // Parse the markdown content
      const parsedContent = marked.parse(message.content) as string;
      
      // Create a DOM parser to work with the HTML content
      const parser = new DOMParser();
      const doc = parser.parseFromString(parsedContent, 'text/html');
      
      // Process HTML elements recursively
      const processElement = (element: Element, level = 0, listIndex = 0): void => {
        // Process child nodes
        Array.from(element.childNodes).forEach((node) => {
          // Text node handling
          if (node.nodeType === Node.TEXT_NODE && node.textContent && node.textContent.trim()) {
            const text = node.textContent.trim();
            if (text) {
              // Split text to fit within page width
              const lines = pdf.splitTextToSize(text, contentWidth - (level * 5));
              
              // Add each line
              lines.forEach((line: string) => {
                // Check if we need a new page
                if (yPosition > pageHeight - margin) {
                  pdf.addPage();
                  yPosition = margin + 10;
                }
                
                // Add text with proper indentation for lists
                pdf.text(line, margin + (level * 5), yPosition);
                yPosition += normalLineHeight;
              });
            }
            return;
          }
          
          // Element node handling
          if (node.nodeType === Node.ELEMENT_NODE) {
            const elem = node as Element;
            
            // Handle different types of elements
            switch(elem.tagName.toLowerCase()) {
              case 'h1':
              case 'h2':
              case 'h3':
              case 'h4':
              case 'h5':
              case 'h6':
                // Get heading level
                const headingLevel = parseInt(elem.tagName.substring(1));
                
                // Calculate size based on heading level (h1 = 18, h2 = 16, etc.)
                const fontSize = Math.max(20 - (headingLevel * 2), 11);
                
                // Add space before heading
                yPosition += normalLineHeight;
                
                // Set heading style
                pdf.setFont('helvetica', 'bold');
                pdf.setFontSize(fontSize);
                pdf.setTextColor(60, 60, 60);
                
                // Get text and add to PDF
                if (elem.textContent) {
                  const headingText = elem.textContent.trim();
                  const lines = pdf.splitTextToSize(headingText, contentWidth);
                  
                  lines.forEach((line: string) => {
                    // Check for page break
                    if (yPosition > pageHeight - margin) {
                      pdf.addPage();
                      yPosition = margin + 10;
                    }
                    
                    pdf.text(line, margin, yPosition);
                    yPosition += normalLineHeight * 1.2;
                  });
                }
                
                // Add some space after heading
                yPosition += normalLineHeight * 0.5;
                
                // Reset to normal text style
                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(11);
                pdf.setTextColor(80, 80, 80);
                break;
                
              case 'p':
                // Process paragraph content
                processElement(elem, level);
                
                // Add extra space after paragraph
                yPosition += normalLineHeight * 0.7;
                break;
                
              case 'strong':
              case 'b':
                // Set bold font
                pdf.setFont('helvetica', 'bold');
                processElement(elem, level);
                pdf.setFont('helvetica', 'normal');
                break;
                
              case 'em':
              case 'i':
                // Set italic font
                pdf.setFont('helvetica', 'italic');
                processElement(elem, level);
                pdf.setFont('helvetica', 'normal');
                break;
                
              case 'ul':
                // Process all list items with increased indentation
                Array.from(elem.children).forEach((child) => {
                  if (child.tagName.toLowerCase() === 'li') {
                    // Check for page break
                    if (yPosition > pageHeight - margin) {
                      pdf.addPage();
                      yPosition = margin + 10;
                    }
                    
                    // Draw bullet point
                    pdf.circle(margin + (level * 5) + 1.5, yPosition - 2.5, 0.8, 'F');
                    
                    // Process list item with indentation
                    processElement(child, level + 1);
                    
                    // Extra space after list item
                    yPosition += normalLineHeight * 0.5;
                  }
                });
                break;
                
              case 'ol':
                // Process ordered list
                let counter = 1;
                Array.from(elem.children).forEach((child) => {
                  if (child.tagName.toLowerCase() === 'li') {
                    // Check for page break
                    if (yPosition > pageHeight - margin) {
                      pdf.addPage();
                      yPosition = margin + 10;
                    }
                    
                    // Add number
                    pdf.text(`${counter}.`, margin + (level * 5), yPosition);
                    
                    // Process list item with indentation
                    processElement(child, level + 2);
                    
                    // Extra space after list item
                    yPosition += normalLineHeight * 0.5;
                    counter++;
                  }
                });
                break;
                
              case 'code':
                // Style code differently
                pdf.setFont('courier', 'normal');
                pdf.setFontSize(10);
                pdf.setTextColor(100, 100, 100);
                
                // Process code content
                processElement(elem, level);
                
                // Reset style
                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(11);
                pdf.setTextColor(80, 80, 80);
                break;
                
              case 'pre':
                // Code blocks
                // Add background if possible
                const codeContent = elem.textContent?.trim() || '';
                
                // Add some space before code block
                yPosition += normalLineHeight * 0.5;
                
                // Set code style
                pdf.setFont('courier', 'normal');
                pdf.setFontSize(9);
                pdf.setTextColor(80, 80, 80);
                
                // Split into lines and add with indentation
                const codeLines = codeContent.split('\n');
                codeLines.forEach((line: string) => {
                  // Check for page break
                  if (yPosition > pageHeight - margin) {
                    pdf.addPage();
                    yPosition = margin + 10;
                  }
                  
                  // Format code with indentation
                  const trimmedLine = line.trimStart(); // Remove leading spaces
                  pdf.text(trimmedLine, margin + 5, yPosition);
                  yPosition += normalLineHeight * 0.9;
                });
                
                // Add space after code block
                yPosition += normalLineHeight;
                
                // Reset style
                pdf.setFont('helvetica', 'normal');
                pdf.setFontSize(11);
                pdf.setTextColor(80, 80, 80);
                break;
                
              case 'blockquote':
                // Indent and style blockquotes
                pdf.setTextColor(100, 100, 100);
                pdf.setFont('helvetica', 'italic');
                
                // Draw quote line
                const quoteStartY = yPosition - normalLineHeight;
                
                // Process blockquote content
                processElement(elem, level + 1);
                
                // Draw vertical line for quote
                pdf.setDrawColor(220, 220, 220);
                pdf.line(margin + 2, quoteStartY, margin + 2, yPosition);
                
                // Reset style
                pdf.setFont('helvetica', 'normal');
                pdf.setTextColor(80, 80, 80);
                
                // Add space after blockquote
                yPosition += normalLineHeight;
                break;
                
              case 'a':
                // Style links
                pdf.setTextColor(0, 102, 204);
                processElement(elem, level);
                pdf.setTextColor(80, 80, 80);
                break;
                
              case 'table':
                // Basic table support
                // Add space before table
                yPosition += normalLineHeight;
                
                // Process table rows
                Array.from(elem.children).forEach((child) => {
                  if (child.tagName.toLowerCase() === 'thead' || 
                      child.tagName.toLowerCase() === 'tbody') {
                    processElement(child, level);
                  }
                });
                
                // Add space after table
                yPosition += normalLineHeight;
                break;
                
              case 'tr':
                const rowStartY = yPosition;
                
                // Process table cells
                Array.from(elem.children).forEach((cell, cellIndex) => {
                  if (cell.tagName.toLowerCase() === 'th' || 
                      cell.tagName.toLowerCase() === 'td') {
                    
                    // Calculate cell width (simple division)
                    const cellWidth = contentWidth / elem.children.length;
                    const cellX = margin + (cellIndex * cellWidth);
                    
                    // Style headers differently
                    if (cell.tagName.toLowerCase() === 'th') {
                      pdf.setFont('helvetica', 'bold');
                    }
                    
                    // Process cell content with position tracking
                    const cellStartY = yPosition;
                    processElement(cell, level);
                    
                    // Reset style
                    pdf.setFont('helvetica', 'normal');
                  }
                });
                
                // Add separator line after the row
                pdf.setDrawColor(200, 200, 200);
                pdf.line(margin, yPosition, margin + contentWidth, yPosition);
                
                // Small space after row
                yPosition += normalLineHeight * 0.3;
                break;
                
              default:
                // Process other elements
                processElement(elem, level);
            }
          }
        });
      };
      
      // Start processing with the root element
      processElement(doc.body);
      
      // Add footer with page numbers
      const pageCount = pdf.getNumberOfPages();
      for (let i = 1; i <= pageCount; i++) {
        pdf.setPage(i);
        pdf.setFontSize(8);
        pdf.setTextColor(150, 150, 150);
        pdf.text(`Generated by AlignIQ - Page ${i} of ${pageCount}`, margin, pageHeight - 10);
      }
      
      // Save the PDF
      pdf.save(`aligniq-analysis-${new Date().getTime()}.pdf`);
      
      // Dismiss loading toast and show success
      toast.dismiss(loadingToast);
      toast.success('PDF downloaded successfully');
    } catch (error) {
      console.error('PDF generation failed:', error);
      toast.error('Failed to generate PDF');
    }
  };

  // Modify the useEffect that initializes selected messages
  useEffect(() => {
    if (activeConversation && activeConversation.messages) {
      // Ensure each message has an ID and select all by default
      const messagesWithIds = activeConversation.messages.map((msg, index) => {
        // If message doesn't have an ID, add one using index
        if (!msg.id) {
          return { ...msg, id: `temp-id-${index}` };
        }
        return msg;
      });
      
      // Update the conversation with message IDs if needed
      if (messagesWithIds.some((msg, i) => !activeConversation.messages[i].id)) {
        setActiveConversation({
          ...activeConversation,
          messages: messagesWithIds
        });
      }
      
      // Get all message IDs for selection
      const allMessageIds = messagesWithIds.map(msg => msg.id as string);
      console.log('Setting initial message IDs:', allMessageIds);
      setSelectedMessageIds(allMessageIds);
    }
  }, [activeConversation?.id]); // Only run when conversation changes

  // Updated toggle message function with better debugging
  const toggleMessageSelection = (messageId: string) => {
    console.log('Toggling message selection for:', messageId);

    // Update selectedMessageIds state
    setSelectedMessageIds(prev => {
      const newSelection = prev.includes(messageId)
        ? prev.filter(id => id !== messageId)
        : [...prev, messageId];
      console.log('New selection state:', newSelection);
      return newSelection;
    });

    // Also update the 'selected' field in the message object
    setActiveConversation(prev => {
      if (!prev) return null;
      return {
        ...prev,
        messages: prev.messages.map(msg =>
          msg.id === messageId
            ? { ...msg, selected: !msg.selected }
            : msg
        )
      };
    });
  };

  // Debug function to see why checkboxes aren't updating
  const debugSelectionState = (msgId: string) => {
    const isSelected = selectedMessageIds.includes(msgId);
    console.log(`Message ${msgId} selected: ${isSelected}`);
    console.log('All selected IDs:', selectedMessageIds);
    return isSelected;
  };

  // Fix the allMessagesSelected function - it should be a value, not a function call
  const allMessagesSelected = 
    activeConversation?.messages
      .filter(msg => msg.id)
      .every(msg => msg.id && selectedMessageIds.includes(msg.id)) || false;

  // Fix the toggleAllMessages function
  const toggleAllMessages = () => {
    if (activeConversation) {
      const allMessageIds = activeConversation.messages
        .filter(msg => msg.id)
        .map(msg => msg.id as string);

      const shouldSelectAll = !allMessageIds.every(id => selectedMessageIds.includes(id));

      if (shouldSelectAll) {
        // Select all messages
        setSelectedMessageIds(allMessageIds);
        console.log('Selected all messages:', allMessageIds);
      } else {
        // Deselect all messages
        setSelectedMessageIds([]);
        console.log('Deselected all messages');
      }

      // Also update the 'selected' field in all message objects
      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: prev.messages.map(msg => ({
            ...msg,
            selected: shouldSelectAll
          }))
        };
      });
    }
  };

  // Updated Jira integration function to match exact backend flow
  const handleJiraIntegration = () => {
    // Get the authentication token
    const authToken = localStorage.getItem('token') || 
                     localStorage.getItem('regular_token') || 
                     localStorage.getItem('google_auth_token');
    
    if (!authToken) {
      toast.error("Authentication required. Please log in again.");
      return;
    }
    
    // Define popup dimensions
    const width = 600;
    const height = 600;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    
    // Show a loading toast
    const loadingToast = toast.loading("Connecting to Jira...");
    
    // Make the request with proper Authorization header
    fetch(`${API_URL}/auth/jira/login`, {
      method: 'GET',
      headers: {
        'accept': 'application/json',
        'Authorization': `Bearer ${authToken}`
      }
    })
    .then(response => {
      toast.dismiss(loadingToast);
      
      if (!response.ok) {
        throw new Error(`Auth request failed with status: ${response.status}`);
      }
      
      return response.json(); // Expecting JSON with auth_url
    })
    .then(data => {
      console.log("Received auth data:", data);
      
      // Get the auth_url from the response
      const authUrl = data.auth_url || data.url;
      
      if (!authUrl) {
        throw new Error("No authentication URL received from server");
      }
      
      console.log("Opening Jira auth popup to:", authUrl);
      
      // Open the popup with the Atlassian auth URL
      const popup = window.open(
        authUrl,
        'Jira_Authorization',
        `width=${width},height=${height},left=${left},top=${top}`
      );
      
      if (!popup) {
        toast.error("Popup blocked. Please allow popups for this site.");
        return;
      }
      
      // Listen for messages from the popup
      const handleAuthMessage = (event: MessageEvent) => {
        console.log("Received message:", event.origin, event.data);
        
        // Check if this message contains Jira token information
        if (event.data && event.data.type === 'jira_auth_success') {
          // Get the token (check both possible property names)
          const jiraToken = event.data.token || event.data.access_token;
          
          if (jiraToken) {
            console.log("Received Jira token, saving to localStorage");
            
            // Store the token in localStorage
            localStorage.setItem('jira_authorization', jiraToken);
            
            // Close the popup
            popup.close();
            
            // Clean up the event listener
            window.removeEventListener('message', handleAuthMessage);
            
            // Show success message
            toast.success("Successfully connected to Jira!");
            
            // Toggle the panel if it's not already visible
            if (!showIntegrationPanel) {
              setShowIntegrationPanel(true);
            }
            
            // Ensure the Jira tab is active
            setIntegrationTab('jira');
            
            // Trigger UI updates
            window.dispatchEvent(new Event('storage'));
            window.dispatchEvent(new CustomEvent('jiraAuthUpdate'));
          } else {
            console.error("Received success message but no token found");
            toast.error("Authentication successful but no token received");
          }
        }
      };
      
      // Add the message listener
      window.addEventListener('message', handleAuthMessage);
      
      // Clean up if popup is closed manually
      const checkPopup = setInterval(() => {
        if (popup && popup.closed) {
          clearInterval(checkPopup);
          window.removeEventListener('message', handleAuthMessage);
        }
      }, 1000);
    })
    .catch(error => {
      console.error("Error initiating Jira authentication:", error);
      toast.error("Error connecting to Jira: " + error.message);
    });
  };

  // Add these functions for GitHub and Azure (placeholders for now)
  const handleGitHubIntegration = () => {
    toast.success("GitHub integration coming soon!");
    setIntegrationTab('github');
    setShowIntegrationPanel(true);
  };

  const handleAzureIntegration = () => {
    toast.success("Azure DevOps integration coming soon!");
    setIntegrationTab('azure');
    setShowIntegrationPanel(true);
  };

  // Handle selecting a conversation
  const handleSelectConversation = async (conversation: any) => {
    setActiveConversation(conversation);
    setShowUploadUI(false);
  };
  
  // Handle new chat button
  const handleNewChat = () => {
    setActiveConversation(null);
    setShowUploadUI(true);
  };
  
  // Add this function to handle Jira disconnect
  const handleJiraDisconnect = () => {
    localStorage.removeItem('jira_authorization');
    toast.success("Disconnected from Jira");
    
    // Force refresh of the panel
    setShowIntegrationPanel(false);
    setTimeout(() => setShowIntegrationPanel(true), 10);
  };

  // Add a function to handle viewing a Jira issue
  const handleViewJiraIssue = (issueId: string) => {
    console.log("Viewing Jira issue:", issueId);
    setSelectedJiraIssue(issueId);
    setIsSplitView(true);
    setShowIntegrationPanel(false);
  };

  // Add a function to close the split view
  const handleCloseSplitView = () => {
    setIsSplitView(false);
    setSelectedJiraIssue(null);
  };

  // Update the handleProcessFiles function to explicitly support multiple files
  const handleProcessFiles = async () => {
    if (uploadedFiles.length === 0) {
      toast.error('Please upload at least one file');
      return;
    }
    
    setIsProcessing(true);
    
    try {
      // Create a FormData object to send files
      const formData = new FormData();
      
      // Append each file with the field name 'file'
      uploadedFiles.forEach(file => {
        formData.append('file', file);
      });
      
      // Get the token for authentication
      const token = localStorage.getItem('token') || 
                    localStorage.getItem('regular_token') || 
                    localStorage.getItem('google_auth_token');
                  
      if (!token) {
        toast.error('Authentication token not found. Please log in again.');
        setIsProcessing(false);
        return;
      }
      
      // Log what we're sending to the backend
      console.log('Sending files to backend:', uploadedFiles.map(f => f.name));
      
      // Call the backend API to process the files
      const response = await axios.post(`${API_URL}/upload`, formData, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      console.log("Upload response:", response.data);
      
      // Handle successful response
      if (response.data) {
        toast.success(`${uploadedFiles.length} file(s) processed successfully`);

        // Get document_id and analysis mode from the response
        const documentId = response.data.document_id;
        const analysisMode = response.data.analysis_mode || 'full';
        const isPresales = analysisMode === 'presales';
        const presalesId = response.data.presales_id;

        // Get user ID from localStorage
        const userId = localStorage.getItem('user_id');

        let chatHistoryId: string | null = null;

        // Only create chat history for full analysis mode
        if (!isPresales) {
          // Step 2: Save the message to the chat system with the correct payload format
          const chatResponse = await axios.post(`${API_URL}/chat`, {
            user_id: userId,
            document_id: documentId,
            message: [
              {
                role: 'assistant',
                content: response.data.message,
                timestamp: new Date().toISOString(),
                selected: true  // Initial message is selected by default
              }
            ], // Include role, content, timestamp, and selected
            title: response.data.title || `Document Analysis`
          }, {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          });

          console.log("Chat creation response:", chatResponse.data);
          chatHistoryId = chatResponse.data.chat_history_id || response.data.chat_history_id || documentId;
        }

        // Extract P1 blockers and kickstart questions from presales response
        let p1Blockers: P1Blocker[] = [];
        let kickstartQuestions: KickstartQuestion[] = [];
        if (isPresales) {
          // Extract P1 blockers
          if (response.data.p1_blockers) {
            p1Blockers = response.data.p1_blockers;
          }
          // Extract kickstart questions
          if (response.data.kickstart_questions) {
            kickstartQuestions = response.data.kickstart_questions;
          } else if (response.data.blind_spots?.critical_unknowns) {
            kickstartQuestions = response.data.blind_spots.critical_unknowns;
          }
        }

        // Step 3: Create a new conversation with the response data
        const newConversation: Conversation = {
          id: isPresales ? presalesId : (chatHistoryId || documentId),
          title: response.data.title || (uploadedFiles.length > 1
            ? `${uploadedFiles.length} Documents`
            : uploadedFiles[0].name),
          document_id: documentId,
          created_at: new Date().toISOString(),
          messages: [
            {
              role: 'assistant',
              content: response.data.message,
              timestamp: new Date().toISOString(),
              selected: true  // Initial message is selected by default
            }
          ],
          chat_history_id: chatHistoryId,  // null for presales mode
          modified_at: new Date().toISOString(),
          analysis_mode: analysisMode,
          presales_id: presalesId,
          p1_blockers: p1Blockers,
          kickstart_questions: kickstartQuestions,
          blind_spots: response.data.blind_spots
        };

        // Set the active conversation state to trigger the UI update
        setActiveConversation(newConversation);

        // Reset kickstart answers when new presales analysis starts
        if (isPresales) {
          setKickstartAnswers({});
          setShowKickstartPanel(true);  // Auto-show the panel for presales
        }

        // Switch to chat interface
        setShowUploadUI(false);

        // Clear the uploaded files
        setUploadedFiles([]);

        // Only mark data changed and refresh sidebar for full analysis
        if (!isPresales) {
          dataChanged.current = true;

          // Wait briefly to ensure backend has processed the document,
          // then refresh the sidebar once
          setTimeout(async () => {
            await refreshSidebar();
          }, 500);
        }

        // Scroll to the bottom of the chat
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      }
    } catch (error) {
      console.error('Error processing documents:', error);
      
      if (axios.isAxiosError(error) && error.response) {
        const errorDetail = error.response.data?.detail;
        console.log('Error detail:', errorDetail);
        
        if (error.response.status === 401) {
          toast.error('Your session has expired. Please log in again.');
        } else {
          toast.error(`Failed to process documents: ${error.response.data?.message || error.response.data?.detail || 'Unknown error'}`);
        }
      } else {
        toast.error('Failed to process documents. Please try again.');
      }
    } finally {
      setIsProcessing(false);
    }
  };

  // Handle generating full report from presales analysis
  const handleGenerateFullReport = async (assumptionsToUse?: Assumption[]) => {
    if (!activeConversation?.presales_id) {
      toast.error('No pre-sales analysis found');
      return;
    }

    setIsProcessing(true);

    try {
      const token = localStorage.getItem('token') ||
                    localStorage.getItem('regular_token') ||
                    localStorage.getItem('google_auth_token');

      if (!token) {
        toast.error('Authentication token not found. Please log in again.');
        setIsProcessing(false);
        return;
      }

      // Create FormData for the request
      const formData = new FormData();
      formData.append('presales_id', activeConversation.presales_id);

      // Include kickstart answers if any were provided
      if (Object.keys(kickstartAnswers).length > 0) {
        formData.append('user_answers', JSON.stringify(kickstartAnswers));
      }

      // Include assumptions if provided (from readiness analysis)
      if (assumptionsToUse && assumptionsToUse.length > 0) {
        formData.append('assumptions', JSON.stringify(assumptionsToUse));
        console.log(`Generating report with ${assumptionsToUse.length} assumptions`);
      }

      // Call the generate-full-report endpoint
      const response = await axios.post(`${API_URL}/generate-full-report/`, formData, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });

      console.log("Full report response:", response.data);

      if (response.data) {
        toast.success('Full report generated successfully!');

        // Update the conversation with the full report data
        const chatHistoryId = response.data.chat_history_id;

        const updatedConversation: Conversation = {
          ...activeConversation,
          id: chatHistoryId,
          chat_history_id: chatHistoryId,
          analysis_mode: 'full',
          messages: [
            {
              role: 'assistant',
              content: response.data.message,
              timestamp: new Date().toISOString(),
              selected: true
            }
          ],
          title: response.data.title || activeConversation.title
        };

        setActiveConversation(updatedConversation);

        // Reset presales-specific state
        setShowKickstartPanel(false);
        setKickstartAnswers({});

        // Mark data as changed and refresh sidebar
        dataChanged.current = true;
        setTimeout(async () => {
          await refreshSidebar();
        }, 500);
      }
    } catch (error) {
      console.error('Error generating full report:', error);

      if (axios.isAxiosError(error) && error.response) {
        toast.error(`Failed to generate full report: ${error.response.data?.detail || 'Unknown error'}`);
      } else {
        toast.error('Failed to generate full report. Please try again.');
      }
    } finally {
      setIsProcessing(false);
    }
  };

  // Handle presales chat - send message to presales chat endpoint
  const handlePresalesChat = async () => {
    if (!message.trim() || isPresalesChatting || !activeConversation?.presales_id) return;

    setIsPresalesChatting(true);

    try {
      const token = localStorage.getItem('token') ||
                    localStorage.getItem('regular_token') ||
                    localStorage.getItem('google_auth_token');

      if (!token) {
        toast.error('Authentication token not found. Please log in again.');
        return;
      }

      // Add user message to UI immediately
      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
        selected: true
      };

      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: [...prev.messages, userMessage]
        };
      });

      const currentMessage = message;
      setMessage('');

      // Add typing indicator
      const typingMessage: Message = {
        id: 'typing',
        role: 'assistant',
        content: '...',
        timestamp: new Date().toISOString(),
        selected: true
      };

      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: [...prev.messages, typingMessage]
        };
      });

      // Call presales chat endpoint
      const formData = new FormData();
      formData.append('message', currentMessage);

      const response = await axios.post(
        `${API_URL}/presales/${activeConversation.presales_id}/chat`,
        formData,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
          }
        }
      );

      // Remove typing indicator and add real response
      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.data.assistant_message,
        timestamp: new Date().toISOString(),
        selected: true
      };

      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: prev.messages
            .filter(msg => msg.id !== 'typing')
            .concat([assistantMessage])
        };
      });

      // Scroll to bottom
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }, 100);

    } catch (error) {
      console.error('Error in presales chat:', error);
      toast.error('Failed to send message');

      // Remove typing indicator on error
      setActiveConversation(prev => {
        if (!prev) return null;
        return {
          ...prev,
          messages: prev.messages.filter(msg => msg.id !== 'typing')
        };
      });
    } finally {
      setIsPresalesChatting(false);
    }
  };

  // Handle saving answers and running analysis
  const handleSaveAndAnalyze = async () => {
    if (!activeConversation?.presales_id) return;

    setIsAnalyzing(true);

    try {
      const token = localStorage.getItem('token') ||
                    localStorage.getItem('regular_token') ||
                    localStorage.getItem('google_auth_token');

      if (!token) {
        toast.error('Authentication token not found. Please log in again.');
        return;
      }

      // First, save the answers if there are any
      if (Object.keys(kickstartAnswers).length > 0) {
        await axios.post(
          `${API_URL}/presales/${activeConversation.presales_id}/questions/answers`,
          { answers: JSON.stringify(kickstartAnswers) },
          {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/x-www-form-urlencoded'
            }
          }
        );
      }

      // Then run analysis
      const response = await axios.post(
        `${API_URL}/presales/${activeConversation.presales_id}/analyze`,
        {},
        {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      // Store analysis result
      setAnalysisResult({
        readiness: response.data.readiness,
        contradictions: response.data.contradictions || [],
        vague_answers: response.data.vague_answers || [],
        assumptions: response.data.assumptions || [],
        recommendations: response.data.recommendations || [],
        can_generate_report: response.data.can_generate_report
      });

      // Update conversation with new questions state
      if (response.data.questions) {
        setActiveConversation(prev => prev ? {
          ...prev,
          questions: response.data.questions,
          readiness: response.data.readiness
        } : null);
      }

      // Show readiness modal
      setShowReadinessModal(true);

      console.log('Analysis complete:', response.data);

    } catch (error) {
      console.error('Error analyzing answers:', error);
      toast.error('Failed to analyze answers');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Legacy function for backward compatibility
  const handleSaveKickstartAnswers = handleSaveAndAnalyze;

  // Update kickstart/P1 answer - accepts either numeric index for kickstart questions or string key for P1 blockers
  const handleKickstartAnswerChange = (questionKey: number | string, answer: string) => {
    const key = typeof questionKey === 'number' ? `question_${questionKey}` : questionKey;
    setKickstartAnswers(prev => ({
      ...prev,
      [key]: answer
    }));
  };

  // Apply assumptions to answer fields - maps question_id (P1-1, Q4) to frontend keys (p1_0, question_0)
  const handleApplyAssumptions = (assumptions: Assumption[]) => {
    if (!assumptions || assumptions.length === 0) {
      toast.info('No assumptions to apply');
      return;
    }

    const newAnswers: Record<string, string> = { ...kickstartAnswers };
    let appliedCount = 0;

    for (const assumption of assumptions) {
      const questionId = assumption.for_question_id;
      let frontendKey: string | null = null;

      // Map question_id format to frontend key format
      // P1-1, P1-2, etc. → p1_0, p1_1, etc. (1-indexed to 0-indexed)
      if (questionId.startsWith('P1-')) {
        const num = parseInt(questionId.replace('P1-', ''), 10);
        if (!isNaN(num) && num > 0) {
          frontendKey = `p1_${num - 1}`;
        }
      }
      // Q1, Q2, etc. → question_0, question_1, etc. (1-indexed to 0-indexed)
      else if (questionId.startsWith('Q')) {
        const num = parseInt(questionId.replace('Q', ''), 10);
        if (!isNaN(num) && num > 0) {
          frontendKey = `question_${num - 1}`;
        }
      }

      if (frontendKey) {
        // Only apply if the field is currently empty or not set
        if (!newAnswers[frontendKey] || newAnswers[frontendKey].trim() === '') {
          // Format the assumed answer with a marker so user knows it's an assumption
          newAnswers[frontendKey] = `[ASSUMED] ${assumption.assumption}`;
          appliedCount++;
        }
      }
    }

    setKickstartAnswers(newAnswers);
    setShowReadinessModal(false);

    if (appliedCount > 0) {
      toast.success(`Applied ${appliedCount} assumption(s) to answer fields. Review and edit as needed, then Save & Analyze again.`);
    } else {
      toast.info('All assumption fields already have answers');
    }
  };

  // Add/update a useEffect to ensure the integration panel closes when split view is activated
  useEffect(() => {
    // When split view is activated, ensure the integration panel is closed
    if (isSplitView && selectedJiraIssue) {
      setShowIntegrationPanel(false);
    }
  }, [isSplitView, selectedJiraIssue]);

  // Update this function to force a refresh of the sidebar after document upload
  const refreshSidebar = async () => {
    // If a refresh is already in progress or scheduled, don't start another one
    if (refreshInProgress.current) {
      console.log("Refresh already in progress, skipping redundant call");
      return;
    }

    // Skip refresh if no data change has occurred
    if (!dataChanged.current) {
      console.log("No data changes detected, skipping refresh");
      return;
    }

    // If there's a pending timeout, clear it
    if (refreshTimeout.current) {
      clearTimeout(refreshTimeout.current);
      refreshTimeout.current = null;
    }

    // Set a flag to prevent concurrent refreshes
    refreshInProgress.current = true;

    try {
      console.log("Performing sidebar refresh due to data change");
      await fetchConversations();
      
      // Reset data changed flag after successful refresh
      dataChanged.current = false;
      
      // Force a render by making a small state change
      setSidebarExpanded(prev => {
        setTimeout(() => setSidebarExpanded(prev), 50);
        return !prev;
      });
    } catch (error) {
      console.error('Error refreshing sidebar:', error);
    } finally {
      // Clear the flag after a short delay to prevent immediate re-triggers
      refreshTimeout.current = setTimeout(() => {
        refreshInProgress.current = false;
      }, 300);
    }
  };

  // First, add the function to handle adding Jira attachments
  // Add this right before the return statement
  const handleAddJiraAttachment = (file: File) => {
    // Add the file to uploadedFiles state
    setUploadedFiles(prev => [...prev, file]);
    
    // If we're in split view, navigate to the upload UI
    if (isSplitView && isMobile) {
      // For mobile, close the split view and show upload UI
      setIsSplitView(false);
      setShowUploadUI(true);
    } else if (!showUploadUI) {
      // On desktop, we might be in chat view, switch to upload UI
      setShowUploadUI(true);
    }
  };

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e] text-white">
      {/* Use the modular Sidebar component */}
      <Sidebar 
        expanded={sidebarExpanded}
        toggleExpanded={() => setSidebarExpanded(!sidebarExpanded)}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        logout={handleLogout}
        isMobile={isMobile}
        activeConversationId={activeConversation?.id || null}
        groupedConversations={groupedConversations}
        onRefreshConversations={fetchConversations}
      />
      
      {/* Main content area - improved mobile responsiveness */}
      <main 
        className={`flex-1 flex flex-col h-screen overflow-hidden transition-all duration-300 ease-in-out`}
        style={{ 
          position: 'relative',
          width: isMobile ? '100%' : `calc(100% - ${sidebarExpanded ? '16rem' : '4rem'})`,
          marginLeft: isMobile ? (sidebarExpanded ? '0' : '0') : (sidebarExpanded ? '16rem' : '4rem')
        }}
      >
        {/* Main content area with horizontal split view */}
        <div className="flex flex-1 h-full">
          {/* Main content area - improved responsive behavior */}
          <div className={`${isSplitView && !isMobile ? 'w-1/2' : 'w-full'} h-full flex flex-col overflow-hidden`}>
            {activeConversation ? (
              // Chat window
              <div className="flex-1 flex flex-col h-full overflow-hidden">
                {/* Chat header - improved for mobile */}
                <div className="flex-none p-2 md:p-4 border-b border-white/10 flex justify-between items-center bg-indigo-950/50">
                  <h2 className="text-lg md:text-xl font-semibold text-white truncate">{activeConversation.title}</h2>
                </div>
                
                {/* Chat messages - improved scrolling and spacing for mobile */}
                <div className="flex-1 overflow-y-auto p-2 md:p-4 space-y-2 md:space-y-4">
                  {/* Select All checkbox header - improved for mobile */}
                  <div className="sticky top-0 z-10 p-2 md:p-3 bg-[#141332]/90 border-b border-white/10 flex items-center">
                    <label className="flex items-center space-x-2 text-xs md:text-sm text-gray-300">
                      <input 
                        type="checkbox" 
                        checked={allMessagesSelected} 
                        onChange={toggleAllMessages}
                        className="form-checkbox h-3 w-3 md:h-4 md:w-4 rounded text-purple-500"
                      />
                      <span>Include all messages as context</span>
                    </label>
                  </div>
                  
                  <div className="p-2 md:p-4 space-y-4 md:space-y-6">
                    {/* Message rendering - improved for mobile */}
                    {activeConversation && activeConversation.messages.map((msg, index) => (
                      <div key={msg.id || index} className={`mb-2 md:mb-4 flex items-start ${msg.role === 'user' ? 'mr-6 md:mr-12' : 'ml-6 md:ml-12'}`}>
                        {/* Checkbox for message selection */}
                        <div className="mr-1 md:mr-2 mt-2">
                          <input 
                            type="checkbox"
                            checked={msg.id ? debugSelectionState(msg.id) : false}
                            onChange={() => msg.id && toggleMessageSelection(msg.id)}
                            className="form-checkbox h-3 w-3 md:h-4 md:w-4 rounded text-purple-500 cursor-pointer"
                          />
                        </div>
                        
                        {msg.role === 'assistant' ? (
                          // AI message with export options - improved for mobile
                          <div className="flex-1 flex flex-col space-y-1 md:space-y-2 bg-[#1a1745] rounded-lg p-2 md:p-4 max-w-full md:max-w-3xl overflow-hidden">
                            <div className="flex items-start space-x-2 md:space-x-3">
                              <div className="h-6 w-6 md:h-8 md:w-8 rounded-md bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center flex-shrink-0">
                                <span className="text-xs md:text-sm font-bold text-white">AI</span>
                              </div>
                              <div className="flex-1 min-w-0 overflow-hidden">
                                <div className="prose text-gray-100 max-w-none overflow-hidden break-words whitespace-pre-wrap text-sm md:text-base">
                                  {/* Render markdown content */}
                                  <div dangerouslySetInnerHTML={{ 
                                    __html: typeof marked.parse(msg.content) === 'string' 
                                      ? marked.parse(msg.content) as string 
                                      : String(marked.parse(msg.content)) 
                                  }} className="overflow-hidden" />
                                </div>
                                
                                {/* Export options bar - improved for mobile */}
                                <div className="mt-2 md:mt-4 pt-1 md:pt-2 border-t border-white/10 flex justify-end space-x-1 md:space-x-2">
                                  <button 
                                    onClick={() => handleCopyMessage(msg)}
                                    className="flex items-center text-xs text-gray-400 hover:text-white px-1 md:px-2 py-1 rounded hover:bg-white/5 transition-colors"
                                  >
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-3.5 md:w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    Copy
                                  </button>
                                
                                  <button
                                    onClick={() => handleDownloadPDF(msg)}
                                    className="flex items-center text-xs text-gray-400 hover:text-white px-1 md:px-2 py-1 rounded hover:bg-white/5 transition-colors"
                                  >
                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-3.5 md:w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 10v6m0 0l-3-3m3 3l3 3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    <span className="hidden md:inline">Download PDF</span>
                                    <span className="inline md:hidden">PDF</span>
                                  </button>
                                </div>
                              </div>
                            </div>
                          </div>
                        ) : (
                          // User message - improved for mobile
                          <div className="flex-1 bg-[#2b2a63] rounded-lg p-2 md:p-4 max-w-full md:max-w-3xl overflow-hidden">
                            <div className="flex items-start space-x-2 md:space-x-3">
                              <div className="h-6 w-6 md:h-8 md:w-8 rounded-full bg-white/10 flex items-center justify-center flex-shrink-0">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4 text-white" viewBox="0 0 20 20" fill="currentColor">
                                  <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                                </svg>
                              </div>
                              <div className="flex-1 min-w-0 overflow-hidden">
                                <p className="text-white whitespace-pre-wrap break-words overflow-hidden text-sm md:text-base">{msg.content}</p>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                    {/* This empty div is crucial for scrolling */}
                    <div ref={messagesEndRef} className="h-px w-full" />
                  </div>
                </div>
                {/* Chat input - only shown when conversation is active, not in upload mode, and NOT in presales mode */}
                {activeConversation && !showUploadUI && activeConversation.analysis_mode !== 'presales' && (
                  <div className="flex-none p-2 md:p-4 border-t border-white/10 bg-indigo-950/50">
                    <div className="relative">
                      <textarea
                        value={message}
                        onChange={handleMessageChange}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSendMessage();
                          }
                        }}
                        placeholder="Type your message here..."
                        className="w-full px-3 md:px-4 py-2 md:py-3 pr-12 md:pr-16 bg-white/5 border border-white/10 rounded-lg text-white
                          placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500
                          min-h-[40px] md:min-h-[50px] max-h-[96px] overflow-y-auto resize-none text-sm md:text-base"
                        style={{ height: 'auto', lineHeight: '1.5' }}
                        rows={1}
                        ref={textareaRef}
                      />
                      <button
                        onClick={handleSendMessage}
                        disabled={!message.trim() || isSendingMessage}
                        className="absolute right-3 md:right-5 bottom-2 md:bottom-2.5 p-1 md:p-1.5
                          bg-gradient-to-r from-blue-600 to-purple-600 rounded-full
                          border border-purple-500/30 shadow-md text-white
                          hover:from-blue-500 hover:to-purple-500 focus:outline-none
                          disabled:opacity-50 disabled:cursor-not-allowed
                          transition-all duration-200"
                      >
                        {isSendingMessage ? (
                          <svg className="animate-spin h-3 w-3 md:h-4 md:w-4" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                )}

                {/* Pre-sales mode - Chat input and action bar */}
                {activeConversation && !showUploadUI && activeConversation.analysis_mode === 'presales' && (
                  <div className="flex-none border-t border-white/10 bg-indigo-950/50">
                    {/* Presales info bar with buttons */}
                    <div className="p-2 md:p-3 border-b border-white/5 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center px-2 py-1 rounded-full bg-purple-500/20 text-purple-300 text-xs font-medium">
                          Pre-Sales Brief
                        </span>
                        <span className="text-xs text-gray-400 hidden md:inline">
                          Ask questions about the analysis or review kickstart questions
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {/* Toggle Questions Panel (P1 Blockers + Kickstart Questions) */}
                        <button
                          onClick={() => setShowKickstartPanel(!showKickstartPanel)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 flex items-center
                            ${showKickstartPanel
                              ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
                              : 'bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10'}`}
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Questions
                          {((activeConversation.p1_blockers?.length || 0) + (activeConversation.kickstart_questions?.length || 0)) > 0 && (
                            <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-yellow-500/30 text-yellow-200 text-xs">
                              {(activeConversation.p1_blockers?.length || 0) + (activeConversation.kickstart_questions?.length || 0)}
                            </span>
                          )}
                        </button>

                        {/* Generate Full Report Button */}
                        <button
                          onClick={() => handleGenerateFullReport()}
                          disabled={isProcessing}
                          className="px-3 py-1.5 bg-gradient-to-r from-green-600 to-blue-600
                            rounded-lg border border-green-500/30 text-white text-xs font-medium
                            hover:from-green-500 hover:to-blue-500 focus:outline-none
                            disabled:opacity-50 disabled:cursor-not-allowed
                            transition-all duration-200 flex items-center"
                        >
                          {isProcessing ? (
                            <>
                              <svg className="animate-spin h-3.5 w-3.5 mr-1.5" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                              Generating...
                            </>
                          ) : (
                            <>
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              Generate Full Report
                            </>
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Questions Panel - P1 Blockers + Kickstart Questions */}
                    {showKickstartPanel && ((activeConversation.p1_blockers?.length || 0) + (activeConversation.kickstart_questions?.length || 0)) > 0 && (
                      <div className="p-3 md:p-4 border-b border-white/10 bg-yellow-500/5 max-h-80 overflow-y-auto">
                        <div className="flex items-center justify-between mb-3">
                          <h4 className="text-sm font-medium text-yellow-300">Questions <span className="font-normal text-gray-400">(reference by P1-# or Q# in chat)</span></h4>
                          <button
                            onClick={handleSaveAndAnalyze}
                            disabled={isAnalyzing}
                            className="px-2 py-1 bg-yellow-600/20 text-yellow-300 rounded text-xs hover:bg-yellow-600/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                          >
                            {isAnalyzing ? (
                              <>
                                <svg className="animate-spin h-3 w-3 mr-1" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Analyzing...
                              </>
                            ) : (
                              <>Save & Analyze</>
                            )}
                          </button>
                        </div>

                        {/* P1 Blockers Section */}
                        {activeConversation.p1_blockers && activeConversation.p1_blockers.length > 0 && (
                          <div className="mb-4">
                            <h5 className="text-xs font-semibold text-red-400 mb-2 flex items-center">
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                              </svg>
                              P1 Blockers (Must Resolve)
                            </h5>
                            <div className="space-y-3">
                              {activeConversation.p1_blockers.map((p1, index) => (
                                <div key={`p1-${index}`} className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                                  <div className="flex items-start gap-2 mb-2">
                                    <span className="px-1.5 py-0.5 bg-red-500/30 text-red-300 rounded text-xs font-bold shrink-0">
                                      P1-{index + 1}
                                    </span>
                                    <span className="px-1.5 py-0.5 bg-gray-500/20 text-gray-300 rounded text-xs capitalize shrink-0">
                                      {p1.area}
                                    </span>
                                    <p className="text-sm text-white font-medium">{p1.blocker}</p>
                                  </div>
                                  <p className="text-xs text-gray-400 mb-2">
                                    <span className="text-red-400/70">Why it matters:</span> {p1.why_it_matters}
                                  </p>
                                  <p className="text-xs text-white mb-2 bg-white/5 p-2 rounded">
                                    <span className="text-yellow-400">Question:</span> {p1.question}
                                  </p>
                                  <textarea
                                    placeholder={`Enter answer for P1-${index + 1}...`}
                                    value={kickstartAnswers[`p1_${index}`] || ''}
                                    onChange={(e) => handleKickstartAnswerChange(`p1_${index}`, e.target.value)}
                                    className="w-full px-2 py-1.5 bg-white/5 border border-red-500/20 rounded text-sm text-white
                                      placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-red-500/50
                                      resize-none"
                                    rows={2}
                                  />
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Kickstart Questions Section */}
                        {activeConversation.kickstart_questions && activeConversation.kickstart_questions.length > 0 && (
                          <div>
                            <h5 className="text-xs font-semibold text-yellow-400 mb-2 flex items-center">
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                              Kickstart Questions (For Scoping)
                            </h5>
                            <div className="space-y-3">
                              {activeConversation.kickstart_questions.map((q, index) => (
                                <div key={`q-${index}`} className="bg-white/5 rounded-lg p-3">
                                  <div className="flex items-start gap-2 mb-2">
                                    <span className="px-1.5 py-0.5 bg-purple-500/30 text-purple-300 rounded text-xs font-bold shrink-0">
                                      Q{index + 1}
                                    </span>
                                    <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 rounded text-xs capitalize shrink-0">
                                      {q.category}
                                    </span>
                                    <p className="text-sm text-white">{q.question}</p>
                                  </div>
                                  <p className="text-xs text-gray-400 mb-2">
                                    <span className="text-yellow-400/70">Why critical:</span> {q.why_critical}
                                  </p>
                                  <textarea
                                    placeholder={`Enter answer for Q${index + 1}...`}
                                    value={kickstartAnswers[`question_${index}`] || ''}
                                    onChange={(e) => handleKickstartAnswerChange(index, e.target.value)}
                                    className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded text-sm text-white
                                      placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-yellow-500/50
                                      resize-none"
                                    rows={2}
                                  />
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        <p className="mt-3 text-xs text-gray-500 text-center">
                          These answers will be included when generating the full report
                        </p>
                      </div>
                    )}

                    {/* Chat input for presales */}
                    <div className="p-2 md:p-3">
                      <div className="relative">
                        <textarea
                          value={message}
                          onChange={handleMessageChange}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                              e.preventDefault();
                              handlePresalesChat();
                            }
                          }}
                          placeholder="Ask about the analysis (e.g., 'Tell me more about P1-2' or 'Explain Q3')..."
                          className="w-full px-3 md:px-4 py-2 md:py-3 pr-12 md:pr-16 bg-white/5 border border-white/10 rounded-lg text-white
                            placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-purple-500
                            min-h-[40px] md:min-h-[50px] max-h-[96px] overflow-y-auto resize-none text-sm md:text-base"
                          style={{ height: 'auto', lineHeight: '1.5' }}
                          rows={1}
                          ref={textareaRef}
                        />
                        <button
                          onClick={handlePresalesChat}
                          disabled={!message.trim() || isPresalesChatting}
                          className="absolute right-3 md:right-5 bottom-2 md:bottom-2.5 p-1 md:p-1.5
                            bg-gradient-to-r from-purple-600 to-pink-600 rounded-full
                            border border-purple-500/30 shadow-md text-white
                            hover:from-purple-500 hover:to-pink-500 focus:outline-none
                            disabled:opacity-50 disabled:cursor-not-allowed
                            transition-all duration-200"
                        >
                          {isPresalesChatting ? (
                            <svg className="animate-spin h-3 w-3 md:h-4 md:w-4" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                          ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
                            </svg>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              // Upload UI - improved for mobile
              <div className="flex-1 flex flex-col overflow-y-auto bg-indigo-950">
                <div className="max-w-3xl mx-auto w-full py-6 md:py-12 px-4">
                  <div className="text-center mb-4 md:mb-8">
                    <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Upload Your Document</h1>
                    <p className="text-base md:text-lg text-gray-300">Upload a project document to analyze requirements, and get AI assistance</p>
                  </div>
                  
                  <div className="bg-indigo-900/40 border border-white/10 rounded-xl p-4 md:p-8 backdrop-blur-sm">
                    <div className="mb-4 md:mb-6">
                      <h2 className="text-lg md:text-xl font-semibold text-white mb-2">Document Upload</h2>
                      <p className="text-sm md:text-base text-gray-300">Upload project requirements, specifications, or any documents you need to analyze</p>
                    </div>
                    
                    {/* Rest of upload UI with mobile improvements */}
                    {uploadedFiles.length > 0 ? (
                      <div className="mb-4 md:mb-6">
                        <div className="mb-3 flex items-center justify-between">
                          <h3 className="text-white text-sm md:text-base font-medium">Selected Files ({uploadedFiles.length})</h3>
                          <button 
                            onClick={() => setUploadedFiles([])}
                            className="text-xs md:text-sm text-gray-400 hover:text-white flex items-center"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Clear All
                          </button>
                        </div>
                        
                        <div className="max-h-40 overflow-y-auto pr-1 border border-white/10 rounded-lg">
                          {uploadedFiles.map((file, index) => (
                            <div key={index} className="flex items-center p-2 md:p-3 bg-white/5 border-b border-white/10 last:border-b-0">
                              <div className="mr-2 md:mr-3 bg-indigo-600 rounded-md p-1 md:p-1.5 flex-shrink-0">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                              </div>
                              <div className="flex-1 truncate">
                                <p className="text-sm md:text-base font-medium text-white truncate">{file.name}</p>
                                <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(2)} KB</p>
                              </div>
                              <button 
                                onClick={() => {
                                  const newFiles = [...uploadedFiles];
                                  newFiles.splice(index, 1);
                                  setUploadedFiles(newFiles);
                                }}
                                className="ml-2 text-gray-400 hover:text-white flex-shrink-0"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 md:h-4 md:w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            </div>
                          ))}
                        </div>
                        
                        <button
                          onClick={handleProcessFiles}
                          disabled={isProcessing}
                          className="w-full mt-4 py-2 md:py-3 px-4 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600
                            border border-purple-500/30 shadow-md transform transition-all duration-200 
                            hover:translate-y-[-2px] hover:shadow-lg hover:shadow-purple-500/30 
                            hover:from-blue-500 hover:to-purple-500 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed
                            text-sm md:text-base"
                        >
                          <span className="relative z-10 flex items-center justify-center text-white font-semibold">
                            {isProcessing ? (
                              <>
                                <svg className="animate-spin h-4 w-4 md:h-5 md:w-5 mr-2" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Processing...
                              </>
                            ) : (
                              <>
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 md:h-5 md:w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                                </svg>
                                Process Documents
                              </>
                            )}
                          </span>
                        </button>
                      </div>
                    ) : (
                      <div 
                        className="border-2 border-dashed border-white/20 rounded-lg p-6 md:p-12 text-center cursor-pointer hover:border-purple-400/50 transition-colors"
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                            setUploadedFiles(Array.from(e.dataTransfer.files));
                          }
                        }}
                        onClick={() => document.getElementById('fileInput')?.click()}
                      >
                        <input
                          id="fileInput"
                          type="file"
                          className="hidden"
                          onChange={(e) => {
                            if (e.target.files && e.target.files.length > 0) {
                              setUploadedFiles(Array.from(e.target.files));
                            }
                          }}
                          accept=".pdf,.doc,.docx,.txt,.md"
                          multiple
                        />
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 md:h-12 md:w-12 mx-auto text-gray-400 mb-3 md:mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                        </svg>
                        <p className="text-base md:text-lg font-medium text-white mb-1">Drag and drop your files here</p>
                        <p className="text-xs md:text-sm text-gray-400 mb-3 md:mb-4">or click to browse files</p>
                        <p className="text-xs text-gray-500">Supported formats: PDF, DOC, DOCX, TXT, MD</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
          
          {/* Right panel - Jira issue detail (only visible in split view AND on desktop) */}
          {isSplitView && selectedJiraIssue && !isMobile && (
            <div className="w-1/2 border-l border-white/10 overflow-auto bg-indigo-950/80">
              <JiraIssueDetail 
                issueId={selectedJiraIssue} 
                onClose={handleCloseSplitView}
                onAddAttachmentToAnalysis={handleAddJiraAttachment}
              />
            </div>
          )}
        </div>
      </main>
      
      {/* For mobile devices, we'll show a modal instead of split view - position fixed for mobile */}
      {isSplitView && selectedJiraIssue && isMobile && (
        <div className="fixed inset-0 z-50 bg-indigo-950/95 overflow-auto">
          <div className="p-4">
            <button 
              onClick={handleCloseSplitView}
              className="mb-4 flex items-center text-sm text-white bg-indigo-700/50 px-3 py-1.5 rounded-lg"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd" />
              </svg>
              Back to Chat
            </button>
            <JiraIssueDetail 
              issueId={selectedJiraIssue} 
              onClose={handleCloseSplitView}
              onAddAttachmentToAnalysis={handleAddJiraAttachment}
            />
          </div>
        </div>
      )}
      
      {/* Add Toast Container at the bottom */}
      <div className="fixed bottom-4 right-4 z-50">
        {/* Toast notifications will appear here */}
      </div>
      
      {/* Readiness Analysis Modal */}
      {showReadinessModal && analysisResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-indigo-950 border border-white/20 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <div className="p-4 border-b border-white/10 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Readiness Analysis</h3>
              <button
                onClick={() => setShowReadinessModal(false)}
                className="p-1 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>

            {/* Modal Content - Scrollable */}
            <div className="p-4 overflow-y-auto max-h-[calc(90vh-140px)]">
              {/* Readiness Score */}
              <div className="mb-6 p-4 bg-white/5 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-300">Readiness Score</span>
                  <span className={`text-lg font-bold ${
                    analysisResult.readiness.score >= 0.8 ? 'text-green-400' :
                    analysisResult.readiness.score >= 0.5 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {Math.round(analysisResult.readiness.score * 100)}%
                  </span>
                </div>
                <div className="w-full bg-white/10 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      analysisResult.readiness.score >= 0.8 ? 'bg-green-500' :
                      analysisResult.readiness.score >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${analysisResult.readiness.score * 100}%` }}
                  />
                </div>
                <p className="mt-2 text-sm text-gray-400">
                  {analysisResult.readiness.summary || `Status: ${analysisResult.readiness.status.replace(/_/g, ' ')}`}
                </p>
              </div>

              {/* Contradictions */}
              {analysisResult.contradictions.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-red-400 mb-2 flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    Contradictions Found ({analysisResult.contradictions.length})
                  </h4>
                  <div className="space-y-2">
                    {analysisResult.contradictions.map((c, i) => (
                      <div key={i} className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-sm">
                        <p className="text-white font-medium">{c.description}</p>
                        <p className="text-gray-400 mt-1">{c.explanation}</p>
                        <p className="text-yellow-300 mt-1 text-xs">Fix: {c.suggested_resolution}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Vague Answers */}
              {analysisResult.vague_answers.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-yellow-400 mb-2 flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Vague Answers ({analysisResult.vague_answers.length})
                  </h4>
                  <div className="space-y-2">
                    {analysisResult.vague_answers.map((v, i) => (
                      <div key={i} className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-sm">
                        <p className="text-white"><span className="font-medium">{v.question_id}:</span> {v.issue}</p>
                        <p className="text-gray-400 mt-1">Expected: {v.expected_format}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Assumptions */}
              {analysisResult.assumptions.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-blue-400 mb-2 flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    Assumptions to be Made ({analysisResult.assumptions.length})
                  </h4>
                  <div className="space-y-2">
                    {analysisResult.assumptions.map((a, i) => (
                      <div key={i} className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-sm">
                        <div className="flex items-start justify-between">
                          <p className="text-white">{a.assumption}</p>
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            a.risk_level === 'high' ? 'bg-red-500/20 text-red-300' :
                            a.risk_level === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                            'bg-green-500/20 text-green-300'
                          }`}>
                            {a.risk_level} risk
                          </span>
                        </div>
                        <p className="text-gray-400 mt-1 text-xs">For: {a.for_question_id}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {analysisResult.recommendations.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-semibold text-green-400 mb-2">Recommendations</h4>
                  <ul className="space-y-1 text-sm text-gray-300">
                    {analysisResult.recommendations.map((r, i) => (
                      <li key={i} className="flex items-start">
                        <span className="text-green-400 mr-2">•</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-white/10 flex items-center justify-between gap-3">
              <button
                onClick={() => setShowReadinessModal(false)}
                className="px-4 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 text-sm"
              >
                Back to Edit
              </button>
              {analysisResult.assumptions.length > 0 ? (
                <button
                  onClick={() => handleApplyAssumptions(analysisResult.assumptions)}
                  disabled={analysisResult.contradictions.length > 0}
                  className="px-4 py-2 bg-gradient-to-r from-yellow-600 to-orange-600 text-white rounded-lg hover:from-yellow-500 hover:to-orange-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center"
                >
                  Apply {analysisResult.assumptions.length} Assumptions
                </button>
              ) : (
                <button
                  onClick={() => {
                    setShowReadinessModal(false);
                    handleGenerateFullReport();
                  }}
                  disabled={!analysisResult.can_generate_report}
                  className="px-4 py-2 bg-gradient-to-r from-green-600 to-blue-600 text-white rounded-lg hover:from-green-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center"
                >
                  Generate Full Report
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Integration panel - improved for mobile */}
      <RightSidebar
        onJiraConnect={handleJiraIntegration}
        onGitHubConnect={handleGitHubIntegration}
        onAzureConnect={handleAzureIntegration}
        jiraToken={localStorage.getItem('jira_authorization')}
        onViewJiraIssue={handleViewJiraIssue}
        isVisible={showIntegrationPanel}
        onTogglePanel={setShowIntegrationPanel}
        isSplitView={isSplitView}
      />
    </div>
  );
};

export default Dashboard;