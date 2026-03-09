// @ts-nocheck
'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Filter,
  Send,
  Paperclip,
  Phone,
  Video,
  MoreVertical,
  ArrowLeft,
  X,
  MessageSquare,
  Bot,
  User,
  Clock,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/Avatar';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { apiClient } from '@/lib/api-client';
import { useRealtimeConversations } from '@/hooks/useRealtimeConversations';

// Types
interface Conversation {
  id: string;
  contactName: string;
  contactAvatar: string;
  channel: 'email' | 'phone' | 'chat' | 'whatsapp';
  status: 'open' | 'closed' | 'handoff';
  lastMessage: string;
  lastMessageTime: string;
  unreadCount: number;
  messages?: Message[];
}

interface Message {
  id: string;
  sender: 'customer' | 'ai' | 'system';
  content: string;
  timestamp: string;
  avatar?: string;
}

// Mock data for demo
const mockConversations: Conversation[] = [
  {
    id: 'conv-1',
    contactName: 'Sarah Johnson',
    contactAvatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Sarah',
    channel: 'chat',
    status: 'open',
    lastMessage: "Thanks for your help! I'll check that out.",
    lastMessageTime: '2 min ago',
    unreadCount: 2,
  },
  {
    id: 'conv-2',
    contactName: 'Michael Chen',
    contactAvatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Michael',
    channel: 'email',
    status: 'open',
    lastMessage: 'Can you help me with billing?',
    lastMessageTime: '15 min ago',
    unreadCount: 0,
  },
  {
    id: 'conv-3',
    contactName: 'Emma Davis',
    contactAvatar: 'https://api.dicebear.com/7.x/avataaars/svg?seed=Emma',
    channel: 'whatsapp',
    status: 'closed',
    lastMessage: 'Issue resolved. Thank you!',
    lastMessageTime: '1 hour ago',
    unreadCount: 0,
  },
];

const mockMessages: Record<string, Message[]> = {
  'conv-1': [
    {
      id: 'msg-1',
      sender: 'customer',
      content: 'Hi, I need help with my account setup.',
      timestamp: '10:30 AM',
    },
    {
      id: 'msg-2',
      sender: 'ai',
      content:
        "I'd be happy to help! Can you tell me what specific issue you're facing with your account setup?",
      timestamp: '10:31 AM',
    },
    {
      id: 'msg-3',
      sender: 'customer',
      content: "I can't seem to verify my email address.",
      timestamp: '10:32 AM',
    },
    {
      id: 'msg-4',
      sender: 'ai',
      content:
        "Let me walk you through the verification process. First, check your spam folder to ensure the verification email didn't end up there.",
      timestamp: '10:33 AM',
    },
    {
      id: 'msg-5',
      sender: 'system',
      content: 'Conversation transferred to agent Sarah Mitchell',
      timestamp: '10:35 AM',
    },
    {
      id: 'msg-6',
      sender: 'customer',
      content: "Thanks for your help! I'll check that out.",
      timestamp: '10:36 AM',
    },
  ],
  'conv-2': [
    {
      id: 'msg-1',
      sender: 'customer',
      content: 'Can you help me with billing?',
      timestamp: '10:15 AM',
    },
    {
      id: 'msg-2',
      sender: 'ai',
      content:
        "Of course! I can help with billing inquiries. What's your question?",
      timestamp: '10:16 AM',
    },
  ],
};

const channelConfig = {
  email: { color: 'bg-blue-100 text-blue-800', icon: '✉️' },
  phone: { color: 'bg-green-100 text-green-800', icon: '📞' },
  chat: { color: 'bg-purple-100 text-purple-800', icon: '💬' },
  whatsapp: { color: 'bg-green-100 text-green-800', icon: '💬' },
};

// Skeleton Loader
const ConversationSkeleton = () => (
  <div className="space-y-3 p-4">
    {[1, 2, 3].map((i) => (
      <div key={i} className="flex gap-3 animate-pulse">
        <div className="h-12 w-12 rounded-full bg-gray-300 dark:bg-gray-600" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-gray-300 dark:bg-gray-600 rounded w-3/4" />
          <div className="h-3 bg-gray-300 dark:bg-gray-600 rounded w-full" />
        </div>
      </div>
    ))}
  </div>
);

const ChatSkeleton = () => (
  <div className="space-y-4 p-4">
    {[1, 2, 3].map((i) => (
      <div
        key={i}
        className={`flex ${i % 2 === 0 ? 'justify-end' : 'justify-start'} animate-pulse`}
      >
        <div
          className={`h-12 rounded-lg ${i % 2 === 0 ? 'w-2/3' : 'w-1/2'} ${i % 2 === 0 ? 'bg-blue-300' : 'bg-gray-300 dark:bg-gray-600'}`}
        />
      </div>
    ))}
  </div>
);

// Typing Indicator Component
const TypingIndicator = () => (
  <div className="flex gap-2">
    <motion.div
      className="h-2 w-2 rounded-full bg-gray-400"
      animate={{ y: [0, -4, 0] }}
      transition={{ duration: 0.6, repeat: Infinity }}
    />
    <motion.div
      className="h-2 w-2 rounded-full bg-gray-400"
      animate={{ y: [0, -4, 0] }}
      transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }}
    />
    <motion.div
      className="h-2 w-2 rounded-full bg-gray-400"
      animate={{ y: [0, -4, 0] }}
      transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }}
    />
  </div>
);

// Message Component
const MessageBubble: React.FC<{
  message: Message;
  isOwn: boolean;
}> = ({ message, isOwn }) => {
  if (message.sender === 'system') {
    return (
      <div className="flex justify-center py-4">
        <p className="text-xs italic text-gray-500 dark:text-gray-400">
          {message.content}
        </p>
      </div>
    );
  }

  return (
    <motion.div
      className={`flex gap-2 ${isOwn ? 'justify-end' : 'justify-start'}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {!isOwn && (
        <div className="flex-shrink-0">
          <Bot className="h-6 w-6 text-gray-400" />
        </div>
      )}
      <div
        className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
          isOwn
            ? 'bg-primary text-primary-foreground rounded-br-none'
            : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-none'
        }`}
      >
        <p className="text-sm">{message.content}</p>
        <p className={`text-xs mt-1 ${isOwn ? 'text-primary-foreground/70' : 'text-gray-500 dark:text-gray-400'}`}>
          {message.timestamp}
        </p>
      </div>
    </motion.div>
  );
};

// Main Component
export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [filter, setFilter] = useState<'all' | 'open' | 'closed' | 'handoff'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Real-time WebSocket ──
  const {
    connectionState,
    isConnected: wsConnected,
    typingStates,
    sendTyping,
    sendMessage: wsSendMessage,
    markRead,
  } = useRealtimeConversations({
    activeConversationId: selectedConversation?.id || null,
    onNewMessage: (msg) => {
      // Append incoming message to chat view if it's for the active conversation
      if (selectedConversation && msg.conversation_id === selectedConversation.id) {
        const newMsg: Message = {
          id: msg.id,
          sender: msg.sender,
          content: msg.content,
          timestamp: new Date(msg.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          }),
        };
        setMessages((prev) => {
          // Deduplicate by id
          if (prev.some((m) => m.id === newMsg.id)) return prev;
          return [...prev, newMsg];
        });
        setIsTyping(false);
      }

      // Update conversation list preview
      setConversations((prev) =>
        prev.map((c) =>
          c.id === msg.conversation_id
            ? {
                ...c,
                lastMessage: msg.content,
                lastMessageTime: 'Just now',
                unreadCount: c.id === selectedConversation?.id ? 0 : c.unreadCount + 1,
              }
            : c
        )
      );
    },
    onConversationUpdate: (event) => {
      if (event.type === 'conversation_closed') {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === event.conversation_id ? { ...c, status: 'closed' } : c
          )
        );
      } else if (event.type === 'conversation_assigned') {
        setConversations((prev) =>
          prev.map((c) =>
            c.id === event.conversation_id ? { ...c, status: 'handoff' } : c
          )
        );
      }
    },
    onTypingChange: (convId, typing, senderType) => {
      if (selectedConversation?.id === convId && senderType === 'ai') {
        setIsTyping(typing);
      }
    },
  });

  // Load conversations
  useEffect(() => {
    const loadConversations = async () => {
      try {
        setIsLoading(true);
        const response = await apiClient.get('/conversations/api/v1/list');
        setConversations(response.data || mockConversations);
      } catch (error) {
        console.error('Failed to load conversations', error);
        setConversations(mockConversations);
      } finally {
        setIsLoading(false);
      }
    };

    loadConversations();
  }, []);

  // Load conversation messages + mark as read
  useEffect(() => {
    const loadMessages = async () => {
      if (!selectedConversation) {
        setMessages([]);
        return;
      }

      try {
        const response = await apiClient.get(
          `/conversations/api/v1/${selectedConversation.id}`
        );
        setMessages(response.data?.messages || mockMessages[selectedConversation.id] || []);

        // Mark conversation as read via WebSocket
        markRead(selectedConversation.id);

        // Clear unread badge locally
        setConversations((prev) =>
          prev.map((c) =>
            c.id === selectedConversation.id ? { ...c, unreadCount: 0 } : c
          )
        );
      } catch (error) {
        console.error('Failed to load messages', error);
        setMessages(mockMessages[selectedConversation.id] || []);
      }
    };

    loadMessages();
  }, [selectedConversation, markRead]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle window resize for mobile
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Send message — REST API + WebSocket for real-time delivery
  const handleSendMessage = useCallback(async () => {
    if (!inputValue.trim() || !selectedConversation) return;

    const msgContent = inputValue.trim();
    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      sender: 'customer',
      content: msgContent,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    // Optimistic append
    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsSending(true);

    // Stop typing indicator (we're sending)
    sendTyping(selectedConversation.id, false);

    try {
      // Send via REST (persists to DB) — AI response comes back over WebSocket
      await apiClient.post(`/conversations/api/v1/${selectedConversation.id}/message`, {
        content: msgContent,
      });

      // Also broadcast over WebSocket for multi-tab/multi-agent visibility
      wsSendMessage(selectedConversation.id, msgContent);
    } catch (error) {
      console.error('Failed to send message', error);
    } finally {
      setIsSending(false);
    }
  }, [inputValue, selectedConversation, sendTyping, wsSendMessage]);

  // Send typing indicator as user types
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setInputValue(e.target.value);
      if (selectedConversation && e.target.value.trim()) {
        sendTyping(selectedConversation.id, true);
      } else if (selectedConversation) {
        sendTyping(selectedConversation.id, false);
      }
    },
    [selectedConversation, sendTyping]
  );

  // Close conversation
  const handleCloseConversation = useCallback(async () => {
    if (!selectedConversation) return;

    try {
      await apiClient.post(`/conversations/api/v1/${selectedConversation.id}/close`);
      setConversations((prev) =>
        prev.map((c) =>
          c.id === selectedConversation.id ? { ...c, status: 'closed' } : c
        )
      );
      setSelectedConversation(null);
    } catch (error) {
      console.error('Failed to close conversation', error);
    }
  }, [selectedConversation]);

  // Handoff to agent
  const handleHandoff = useCallback(async () => {
    if (!selectedConversation) return;

    try {
      await apiClient.post('/handoff/api/v1/create', {
        conversationId: selectedConversation.id,
      });
      setConversations((prev) =>
        prev.map((c) =>
          c.id === selectedConversation.id ? { ...c, status: 'handoff' } : c
        )
      );
      const systemMessage: Message = {
        id: `msg-${Date.now()}`,
        sender: 'system',
        content: 'Conversation transferred to agent. An agent will assist you shortly.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, systemMessage]);
    } catch (error) {
      console.error('Failed to handoff conversation', error);
    }
  }, [selectedConversation]);

  // Filter conversations
  const filteredConversations = conversations.filter((conv) => {
    const matchesFilter =
      filter === 'all' || conv.status === filter;
    const matchesSearch =
      conv.contactName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      conv.lastMessage.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const showListView = isMobile ? !selectedConversation : true;
  const showChatView = isMobile ? selectedConversation : true;

  return (
    <div className="flex h-screen bg-white dark:bg-gray-950">
      {/* Left Panel - Conversation List */}
      <AnimatePresence mode="wait">
        {showListView && (
          <motion.div
            className="w-full md:w-96 border-r border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-gray-900"
            initial={isMobile ? { x: -400 } : undefined}
            animate={isMobile ? { x: 0 } : undefined}
            exit={isMobile ? { x: -400 } : undefined}
            transition={{ duration: 0.3 }}
          >
            {/* Header */}
            <div className="border-b border-gray-200 dark:border-gray-800 p-4">
              <div className="flex items-center justify-between mb-4">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Conversations
                </h1>
                <div className="flex items-center gap-1.5" title={`WebSocket: ${connectionState}`}>
                  {wsConnected ? (
                    <Wifi className="h-4 w-4 text-green-500" />
                  ) : (
                    <WifiOff className="h-4 w-4 text-gray-400 animate-pulse" />
                  )}
                  <span className={`text-xs ${wsConnected ? 'text-green-500' : 'text-gray-400'}`}>
                    {wsConnected ? 'Live' : connectionState === 'reconnecting' ? 'Reconnecting...' : 'Offline'}
                  </span>
                </div>
              </div>

              {/* Search Bar */}
              <div className="relative mb-4">
                <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search conversations..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              {/* Filter Dropdown */}
              <div className="flex gap-2 overflow-x-auto">
                {[
                  { label: 'All', value: 'all' as const },
                  { label: 'Open', value: 'open' as const },
                  { label: 'Closed', value: 'closed' as const },
                  { label: 'Handoff', value: 'handoff' as const },
                ].map((option) => (
                  <Button
                    key={option.value}
                    variant={filter === option.value ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFilter(option.value)}
                    className="whitespace-nowrap"
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>

            {/* Conversation List */}
            <div className="flex-1 overflow-y-auto">
              {isLoading ? (
                <ConversationSkeleton />
              ) : filteredConversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-4">
                  <MessageSquare className="h-12 w-12 text-gray-300 dark:text-gray-700 mb-4" />
                  <p className="text-gray-600 dark:text-gray-400">
                    No conversations yet. Your AI assistant will handle incoming messages.
                  </p>
                </div>
              ) : (
                <motion.div layout className="space-y-1 p-2">
                  {filteredConversations.map((conv) => (
                    <motion.button
                      key={conv.id}
                      layout
                      onClick={() => setSelectedConversation(conv)}
                      className={`w-full text-left p-3 rounded-lg transition-colors ${
                        selectedConversation?.id === conv.id
                          ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-primary'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                      }`}
                      whileHover={{ x: 4 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <div className="flex gap-3">
                        <Avatar className="h-12 w-12 flex-shrink-0">
                          <AvatarImage src={conv.contactAvatar} />
                          <AvatarFallback>{conv.contactName.charAt(0)}</AvatarFallback>
                        </Avatar>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                              {conv.contactName}
                            </h3>
                            {conv.unreadCount > 0 && (
                              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white flex-shrink-0">
                                {conv.unreadCount}
                              </span>
                            )}
                          </div>

                          <p className="text-sm text-gray-600 dark:text-gray-400 truncate">
                            {conv.lastMessage}
                          </p>

                          <div className="flex items-center gap-2 mt-2">
                            <Badge
                              variant="secondary"
                              className={`text-xs ${channelConfig[conv.channel]?.color}`}
                            >
                              {channelConfig[conv.channel]?.icon} {conv.channel}
                            </Badge>
                            <span className="text-xs text-gray-500 dark:text-gray-500 flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {conv.lastMessageTime}
                            </span>
                          </div>
                        </div>
                      </div>
                    </motion.button>
                  ))}
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Right Panel - Chat View */}
      <AnimatePresence mode="wait">
        {showChatView && (
          <motion.div
            className="flex-1 flex flex-col bg-gray-50 dark:bg-gray-950"
            initial={isMobile ? { x: 400 } : undefined}
            animate={isMobile ? { x: 0 } : undefined}
            exit={isMobile ? { x: 400 } : undefined}
            transition={{ duration: 0.3 }}
          >
            {!selectedConversation ? (
              // Empty state
              <div className="flex flex-col items-center justify-center h-full">
                <MessageSquare className="h-16 w-16 text-gray-300 dark:text-gray-700 mb-4" />
                <p className="text-gray-600 dark:text-gray-400 text-center">
                  Select a conversation to view
                </p>
              </div>
            ) : (
              <>
                {/* Chat Header */}
                <div className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {isMobile && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setSelectedConversation(null)}
                        >
                          <ArrowLeft className="h-5 w-5" />
                        </Button>
                      )}

                      <Avatar className="h-10 w-10">
                        <AvatarImage src={selectedConversation.contactAvatar} />
                        <AvatarFallback>
                          {selectedConversation.contactName.charAt(0)}
                        </AvatarFallback>
                      </Avatar>

                      <div>
                        <h2 className="font-semibold text-gray-900 dark:text-white">
                          {selectedConversation.contactName}
                        </h2>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="secondary"
                            className={channelConfig[selectedConversation.channel]?.color}
                          >
                            {selectedConversation.channel}
                          </Badge>
                          <Badge
                            variant={selectedConversation.status === 'open' ? 'default' : 'secondary'}
                          >
                            {selectedConversation.status}
                          </Badge>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleHandoff}
                        disabled={selectedConversation.status !== 'open'}
                      >
                        <Phone className="h-5 w-5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleCloseConversation}
                        disabled={selectedConversation.status !== 'open'}
                      >
                        <X className="h-5 w-5" />
                      </Button>
                      <Button variant="ghost" size="icon">
                        <MoreVertical className="h-5 w-5" />
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Messages Container */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                  {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full">
                      <MessageSquare className="h-12 w-12 text-gray-300 dark:text-gray-700 mb-4" />
                      <p className="text-gray-500 dark:text-gray-400">
                        No messages yet. Start the conversation!
                      </p>
                    </div>
                  ) : (
                    <>
                      {messages.map((msg) => (
                        <MessageBubble
                          key={msg.id}
                          message={msg}
                          isOwn={msg.sender === 'customer'}
                        />
                      ))}
                      {isTyping && (
                        <div className="flex gap-2 p-3">
                          <Bot className="h-6 w-6 text-gray-400 flex-shrink-0" />
                          <TypingIndicator />
                        </div>
                      )}
                      <div ref={messagesEndRef} />
                    </>
                  )}
                </div>

                {/* Input Bar */}
                <div className="border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                  <div className="flex gap-3">
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={isSending}
                      className="flex-shrink-0"
                    >
                      <Paperclip className="h-5 w-5" />
                    </Button>

                    <input
                      type="text"
                      placeholder="Type your message..."
                      value={inputValue}
                      onChange={handleInputChange}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                      disabled={isSending || selectedConversation.status !== 'open'}
                      className="flex-1 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                    />

                    <Button
                      onClick={handleSendMessage}
                      disabled={isSending || !inputValue.trim() || selectedConversation.status !== 'open'}
                      className="flex-shrink-0"
                    >
                      <Send className="h-5 w-5" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
