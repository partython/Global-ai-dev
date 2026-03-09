/**
 * Onboarding Wizard — Zustand Store
 *
 * Manages the multi-step onboarding flow:
 *   Step 1: Business Profile (industry, country, timezone)
 *   Step 2: Channel Connections (WhatsApp, Email, SMS, Voice, WebChat)
 *   Step 3: AI Configuration (persona, tone, intents, prohibited topics)
 *   Step 4: Test Conversation (live AI test)
 *   Step 5: Go Live
 *
 * Persisted to localStorage so users can resume onboarding.
 * Calls Tenant Config Service (port 9042) via gateway (port 9000).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

// ─── Types ───

export type OnboardingStep =
  | "business_setup"
  | "channels"
  | "ai_config"
  | "knowledge_base"
  | "launch";

export interface BusinessProfile {
  company_name: string;
  industry: string;
  timezone: string;
  language: string;
  website: string;
  logo_url: string;
  country?: string;
  currency?: string;
  support_email?: string;
  phone?: string;
  description?: string;
}

export interface ChannelConfig {
  channel_type: string;
  enabled: boolean;
  credentials: Record<string, string>;
  status: "not_started" | "connecting" | "connected" | "failed";
  error?: string;
}

export interface AIConfig {
  brand_name: string;
  ai_persona_name: string;
  tone_preset: string;
  response_language: string;
  auto_reply_enabled: boolean;
  confidence_threshold: number;
  custom_instructions: string;
  greeting_message: string;
  fallback_message: string;
  escalation_message: string;
  prohibited_topics: string[];
  enabled_intents: string[];
  max_response_length: number;
}

export interface KnowledgeBaseItem {
  id?: string;
  type: "document" | "url" | "faq";
  title: string;
  content?: string;
  url?: string;
  file_url?: string;
  status: "pending" | "processing" | "completed" | "failed";
  error?: string;
}

export interface OnboardingState {
  currentStep: OnboardingStep;
  completedSteps: OnboardingStep[];
  profile: BusinessProfile;
  channels: ChannelConfig[];
  aiConfig: AIConfig;
  knowledgeBase: KnowledgeBaseItem[];
  testConversationId: string | null;
  isSubmitting: boolean;
  errors: Record<string, string>;

  // Actions
  setStep: (step: OnboardingStep) => void;
  completeStep: (step: OnboardingStep) => void;
  updateProfile: (data: Partial<BusinessProfile>) => void;
  updateChannel: (index: number, data: Partial<ChannelConfig>) => void;
  addChannel: (channel: ChannelConfig) => void;
  removeChannel: (index: number) => void;
  updateAIConfig: (data: Partial<AIConfig>) => void;
  addKnowledgeBaseItem: (item: KnowledgeBaseItem) => void;
  updateKnowledgeBaseItem: (id: string, data: Partial<KnowledgeBaseItem>) => void;
  removeKnowledgeBaseItem: (id: string) => void;
  setTestConversationId: (id: string | null) => void;
  setSubmitting: (v: boolean) => void;
  setError: (field: string, msg: string) => void;
  clearErrors: () => void;
  resetOnboarding: () => void;
}

// ─── Defaults ───

const DEFAULT_PROFILE: BusinessProfile = {
  company_name: "",
  industry: "",
  timezone: "",
  language: "en",
  website: "",
  logo_url: "",
};

const DEFAULT_AI_CONFIG: AIConfig = {
  brand_name: "",
  ai_persona_name: "",
  tone_preset: "professional",
  response_language: "en",
  auto_reply_enabled: true,
  confidence_threshold: 0.7,
  custom_instructions: "",
  greeting_message: "",
  fallback_message: "I'm not sure I understood that. Let me connect you with our team.",
  escalation_message: "Let me connect you with a human agent who can help better.",
  prohibited_topics: [],
  enabled_intents: [],
  max_response_length: 500,
};

const DEFAULT_CHANNELS: ChannelConfig[] = [
  {
    channel_type: "webchat",
    enabled: true,
    credentials: {},
    status: "not_started",
  },
];

// ─── Store ───

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      currentStep: "business_setup",
      completedSteps: [],
      profile: { ...DEFAULT_PROFILE },
      channels: [...DEFAULT_CHANNELS],
      aiConfig: { ...DEFAULT_AI_CONFIG },
      knowledgeBase: [],
      testConversationId: null,
      isSubmitting: false,
      errors: {},

      setStep: (step) => set({ currentStep: step }),

      completeStep: (step) =>
        set((state) => ({
          completedSteps: state.completedSteps.includes(step)
            ? state.completedSteps
            : [...state.completedSteps, step],
        })),

      updateProfile: (data) =>
        set((state) => ({
          profile: { ...state.profile, ...data },
        })),

      updateChannel: (index, data) =>
        set((state) => {
          const channels = [...state.channels];
          if (channels[index]) {
            channels[index] = { ...channels[index], ...data };
          }
          return { channels };
        }),

      addChannel: (channel) =>
        set((state) => ({
          channels: [...state.channels, channel],
        })),

      removeChannel: (index) =>
        set((state) => ({
          channels: state.channels.filter((_, i) => i !== index),
        })),

      updateAIConfig: (data) =>
        set((state) => ({
          aiConfig: { ...state.aiConfig, ...data },
        })),

      addKnowledgeBaseItem: (item) =>
        set((state) => ({
          knowledgeBase: [...state.knowledgeBase, { ...item, id: Math.random().toString(36) }],
        })),

      updateKnowledgeBaseItem: (id, data) =>
        set((state) => ({
          knowledgeBase: state.knowledgeBase.map((item) =>
            item.id === id ? { ...item, ...data } : item
          ),
        })),

      removeKnowledgeBaseItem: (id) =>
        set((state) => ({
          knowledgeBase: state.knowledgeBase.filter((item) => item.id !== id),
        })),

      setTestConversationId: (id) => set({ testConversationId: id }),
      setSubmitting: (v) => set({ isSubmitting: v }),
      setError: (field, msg) =>
        set((state) => ({ errors: { ...state.errors, [field]: msg } })),
      clearErrors: () => set({ errors: {} }),

      resetOnboarding: () =>
        set({
          currentStep: "business_setup",
          completedSteps: [],
          profile: { ...DEFAULT_PROFILE },
          channels: [...DEFAULT_CHANNELS],
          aiConfig: { ...DEFAULT_AI_CONFIG },
          knowledgeBase: [],
          testConversationId: null,
          isSubmitting: false,
          errors: {},
        }),
    }),
    {
      name: "priya-onboarding",
      // SECURITY FIX (FE-001): Strip credentials from localStorage persistence.
      // Credentials are only held in memory during the active session and
      // sent directly to the backend. They are NEVER written to disk.
      partialize: (state) => ({
        currentStep: state.currentStep,
        completedSteps: state.completedSteps,
        profile: state.profile,
        // Strip credentials from channels before persisting
        channels: state.channels.map((ch) => ({
          ...ch,
          credentials: {}, // NEVER persist credentials
        })),
        aiConfig: state.aiConfig,
        knowledgeBase: state.knowledgeBase,
        testConversationId: state.testConversationId,
        // Exclude transient state
        // isSubmitting, errors are NOT persisted
      }),
    }
  )
);
