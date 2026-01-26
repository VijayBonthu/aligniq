import axios from 'axios';

export interface ChatItem {
  chat_history_id: string;
  title: string;
  document_id: string;
  created_at: string;
  modified_at: string;
}

export interface MessageContent {
  role: 'user' | 'system' | 'assistant';
  content: string;
  timestamp?: string;
}

const API_URL = import.meta.env.VITE_API_URL;

// Get user's chat history
export const getChatHistory = async (): Promise<ChatItem[]> => {
  const token = localStorage.getItem('token') || 
                localStorage.getItem('google_auth_token') || 
                localStorage.getItem('regular_token');

  if (!token) {
    throw new Error('Authentication token not found');
  }

  try {
    const response = await axios.get(`${API_URL}/chat`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    console.log('Raw API response:', response.data);
    
    // Extract the user_details
    const userData = response.data.user_details;
    
    // If no data found, return empty array
    if (!userData) {
      console.warn('No chat history data found in response');
      return [];
    }
    
    // If it's already an array of chat items, return it directly
    if (Array.isArray(userData)) {
      return userData;
    }
    
    // If it's a single chat object (not in an array), convert to array
    if (userData && typeof userData === 'object' && userData.chat_history_id) {
      return [userData];
    }
    
    console.error('Unexpected chat history data format:', userData);
    return [];
  } catch (error) {
    console.error('Error fetching chat history:', error);
    return [];
  }
};

// Get messages for a specific chat - update the parsing logic
export const getChatMessages = async (chatId: string): Promise<MessageContent[]> => {
  const token = localStorage.getItem('token') || 
                localStorage.getItem('google_auth_token') || 
                localStorage.getItem('regular_token');

  if (!token) {
    throw new Error('Authentication token not found');
  }
  
  try {
    // First find the chat in the history
    const response = await axios.get(`${API_URL}/chat`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    console.log('Raw API response for messages:', response.data);
    
    const userData = response.data.user_details;
    let targetChat = null;
    
    // Find the chat with the matching ID
    if (Array.isArray(userData)) {
      targetChat = userData.find(chat => chat.chat_history_id === chatId);
    } else if (userData && userData.chat_history_id === chatId) {
      targetChat = userData;
    }
    
    if (!targetChat) {
      console.error(`Chat with ID ${chatId} not found in API response`);
      throw new Error('Chat not found');
    }
    
    console.log('Target chat found:', targetChat);
    
    // Parse the messages from the message field
    if (targetChat.message) {
      try {
        // Handle both string and array formats
        let parsedMessages;
        
        if (typeof targetChat.message === 'string') {
          console.log('Parsing message string:', targetChat.message);
          parsedMessages = JSON.parse(targetChat.message);
        } else {
          // It's already an object/array
          parsedMessages = targetChat.message;
        }
        
        console.log('Parsed messages:', parsedMessages);
        
        // Ensure we return an array
        return Array.isArray(parsedMessages) ? parsedMessages : [parsedMessages];
        
      } catch (error) {
        console.error('Error parsing chat messages:', error);
        return [];
      }
    }
    
    return [];
  } catch (error) {
    console.error('Error fetching chat messages:', error);
    return [];
  }
};

// Save chat to history
export const saveChat = async (
  document_id: string, 
  messages: MessageContent[], 
  title: string,
  chat_history_id?: string
): Promise<{chat_history_id: string}> => {
  const token = localStorage.getItem('token') || 
                localStorage.getItem('google_auth_token') || 
                localStorage.getItem('regular_token');

  if (!token) {
    throw new Error('Authentication token not found');
  }

  try {
    // Get user ID from token - Fixed to use the correct endpoint path parameter
    const tokenResponse = await axios.get(`${API_URL}/decode_token/${token}`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    console.log("Token decode response:", tokenResponse.data);
    
    // Extract user ID from the token data
    const userId = tokenResponse.data.id || 
                  tokenResponse.data.user_id;
    
    if (!userId) {
      throw new Error('User ID not found in token');
    }

    // Prepare chat data
    const chatData = {
      chat_history_id: chat_history_id, // If updating an existing chat
      user_id: userId,
      document_id: document_id,
      message: messages,
      title: title
    };

    console.log("Saving chat with data:", chatData);

    // Send request to save chat
    const response = await axios.post(`${API_URL}/chat`, chatData, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    console.log("Chat save response:", response.data);
    
    return {
      chat_history_id: response.data.chat_history_id
    };
  } catch (error) {
    console.error('Error saving chat:', error);
    throw error;
  }
};

// Delete chat from history
export const deleteChat = async (chatId: string): Promise<{status: string}> => {
  const token = localStorage.getItem('token') || 
                localStorage.getItem('google_auth_token') || 
                localStorage.getItem('regular_token');
  
  if (!token) {
    throw new Error('Authentication token not found');
  }

  try {
    const response = await axios.delete(`${API_URL}/chat/${chatId}`, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });
    
    return {
      status: response.data.status
    };
  } catch (error) {
    console.error('Error deleting chat:', error);
    throw error;
  }
}; 