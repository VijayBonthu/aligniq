import axios from 'axios';
import { GroupedConversations, Conversation, ConversationMetadata, Message } from '../types/conversation';

const API_URL = import.meta.env.VITE_API_URL;

// Get token function to centralize token retrieval
const getToken = () => {
  return localStorage.getItem('regular_token') || 
         localStorage.getItem('token') || 
         localStorage.getItem('google_auth_token');
};

// Fetch all conversations and group them
export const fetchConversations = async (): Promise<GroupedConversations> => {
  try {
    console.log('Fetching conversations...');
    
    // Add cache-busting parameter to avoid stale data
    const response = await axios.get(`${API_URL}/chat?_t=${new Date().getTime()}`, {
      headers: {
        'Authorization': `Bearer ${getToken()}`
      }
    });
    
    console.log('Conversation response:', response.data);

    // Group conversations by date
    const grouped = {
      today: [],
      yesterday: [],
      lastWeek: [],
      older: []
    } as GroupedConversations;

    // Handle the correct response structure where conversations are in user_details array
    if (response.data && response.data.user_details && Array.isArray(response.data.user_details)) {
      // Sort conversations by date (newest first)
      const sortedConversations = [...response.data.user_details].sort((a, b) => 
        new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
      );

      const now = new Date();
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      const lastWeek = new Date(now);
      lastWeek.setDate(lastWeek.getDate() - 7);

      sortedConversations.forEach((conversation: ConversationMetadata) => {
        const convoDate = new Date(conversation.modified_at);
        
        // Group by date
        if (convoDate.toDateString() === now.toDateString()) {
          grouped.today.push(conversation);
        } else if (convoDate.toDateString() === yesterday.toDateString()) {
          grouped.yesterday.push(conversation);
        } else if (convoDate > lastWeek) {
          grouped.lastWeek.push(conversation);
        } else {
          grouped.older.push(conversation);
        }
      });
    }

    console.log('Grouped conversations:', grouped);
    return grouped;
  } catch (error) {
    console.error('Error fetching conversations:', error);
    throw error;
  }
};

// Get a specific conversation by ID
export const getConversation = async (chatHistoryId: string): Promise<Conversation> => {
  try {
    const response = await axios.get(`${API_URL}/chat/${chatHistoryId}`, {
      headers: {
        'Authorization': `Bearer ${getToken()}`
      }
    });
    
    // Extract the user_details if that's where your conversation data is
    if (response.data && response.data.user_details) {
      const details = response.data.user_details;
      
      // Parse messages if needed
      let messages: Message[] = [];
      try {
        if (typeof details.message === 'string') {
          messages = JSON.parse(details.message);
        } else if (Array.isArray(details.message)) {
          messages = details.message;
        }
      } catch (e) {
        console.error("Error parsing messages:", e);
        messages = [];
      }
      
      // Create a conversation object
      return {
        id: details.chat_history_id,
        title: details.title,
        created_at: details.modified_at,
        messages: messages,
        document_id: details.document_id || ''
      };
    }
    
    return response.data;
  } catch (error) {
    console.error('Error loading conversation:', error);
    throw error;
  }
};

// Rename a conversation
export const renameConversation = async (chatId: string, newTitle: string): Promise<void> => {
  try {
    const token = getToken();
    
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
  } catch (error) {
    console.error('Error renaming conversation:', error);
    throw error;
  }
};

// Delete a conversation
export const deleteConversation = async (chatId: string): Promise<void> => {
  try {
    const token = getToken();
    
    // Delete the conversation from the backend
    await axios.delete(`${API_URL}/chat/${chatId}`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
  } catch (error) {
    console.error('Error deleting conversation:', error);
    
    // If we get a 404, the conversation is already gone from backend
    // So we should still return success to clean up the UI
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      return;
    }
    
    throw error;
  }
}; 