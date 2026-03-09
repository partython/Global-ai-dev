"use client";

import { useRouter } from "next/navigation";
import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type FormEvent,
  type ChangeEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2,
  Globe,
  Clock,
  Smartphone,
  Mail,
  Link,
  ChevronRight,
  ChevronLeft,
  Check,
  MessageSquare,
  Bot,
  Zap,
  Sparkles,
  Rocket,
  AlertCircle,
  Loader2,
  Plus,
  X,
  MessageCircle,
  Instagram,
  Facebook,
  AtSign,
  Upload,
  FileText,
  Settings,
  Gauge,
  Users,
  Send,
  Volume2,
  Brain,
  Shield,
  Search,
  Trash2,
} from "lucide-react";
import { useOnboardingStore, type OnboardingStep } from "@/stores/onboarding";
import { useAuthStore } from "@/stores/auth";
import { apiClient } from "@/lib/api";

// ============================================================================
// STEP CONFIGURATION & CONSTANTS
// ============================================================================

const STEPS: { id: OnboardingStep; label: string; icon: any }[] = [
  { id: "business_setup", label: "Business Setup", icon: Building2 },
  { id: "channels", label: "Connect Channels", icon: MessageSquare },
  { id: "ai_config", label: "AI Configuration", icon: Bot },
  { id: "knowledge_base", label: "Knowledge Base", icon: FileText },
  { id: "launch", label: "Launch", icon: Rocket },
];

const INDUSTRIES = [
  { value: "ecommerce", label: "E-Commerce" },
  { value: "saas", label: "SaaS" },
  { value: "healthcare", label: "Healthcare" },
  { value: "education", label: "Education" },
  { value: "finance", label: "Finance" },
  { value: "real_estate", label: "Real Estate" },
  { value: "hospitality", label: "Hospitality" },
  { value: "other", label: "Other" },
];

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Dubai",
  "Australia/Sydney",
];

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "zh", label: "Chinese" },
  { value: "ja", label: "Japanese" },
  { value: "ar", label: "Arabic" },
];

const CHANNELS_AVAILABLE = [
  {
    id: "whatsapp",
    name: "WhatsApp",
    icon: MessageCircle,
    description: "Connect your WhatsApp Business account",
    color: "bg-green-500",
  },
  {
    id: "email",
    name: "Email",
    icon: Mail,
    description: "Support email communications",
    color: "bg-blue-500",
  },
  {
    id: "web",
    name: "Web Widget",
    icon: Globe,
    description: "Embedded chat widget for your website",
    color: "bg-purple-500",
  },
  {
    id: "sms",
    name: "SMS",
    icon: Smartphone,
    description: "SMS text message support",
    color: "bg-orange-500",
  },
  {
    id: "instagram",
    name: "Instagram",
    icon: Instagram,
    description: "Direct messages via Instagram",
    color: "bg-pink-500",
  },
  {
    id: "facebook",
    name: "Facebook",
    icon: Facebook,
    description: "Messenger and page messages",
    color: "bg-blue-600",
  },
];

const AI_PERSONALITIES = [
  {
    id: "professional",
    label: "Professional",
    description: "Formal, business-focused, authoritative",
    examples: [
      "Thank you for your inquiry. How may I assist you?",
      "I'd be happy to help with that.",
    ],
  },
  {
    id: "friendly",
    label: "Friendly",
    description: "Warm, approachable, conversational",
    examples: [
      "Hey! Great to hear from you! How can I help?",
      "Love this question! Let me break it down for you.",
    ],
  },
  {
    id: "casual",
    label: "Casual",
    description: "Relaxed, informal, modern tone",
    examples: [
      "Yo! What's up? What can I do for you?",
      "Sure thing! Here's the lowdown...",
    ],
  },
];

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function OnboardingPage() {
  const router = useRouter();
  const {
    currentStep,
    setStep,
    completeStep,
    updateProfile,
    updateAIConfig,
    addKnowledgeBaseItem,
    updateKnowledgeBaseItem,
    removeKnowledgeBaseItem,
    profile,
    aiConfig,
    knowledgeBase,
    channels,
    isSubmitting,
    setSubmitting,
    errors,
    setError,
    clearErrors,
  } = useOnboardingStore();

  const { user } = useAuthStore();
  const [showConfetti, setShowConfetti] = useState(false);

  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep);

  const handleNext = useCallback(
    async (skipValidation = false) => {
      clearErrors();

      if (!skipValidation) {
        if (currentStep === "business_setup") {
          if (!profile.company_name.trim()) {
            setError("company_name", "Business name is required");
            return;
          }
          if (!profile.industry) {
            setError("industry", "Please select an industry");
            return;
          }
          if (!profile.timezone) {
            setError("timezone", "Please select a timezone");
            return;
          }
          if (!profile.website.trim()) {
            setError("website", "Website URL is required");
            return;
          }
        }

        if (currentStep === "ai_config") {
          if (!aiConfig.ai_persona_name.trim()) {
            setError("ai_persona_name", "AI assistant name is required");
            return;
          }
        }
      }

      completeStep(currentStep);

      if (currentStepIndex < STEPS.length - 1) {
        setStep(STEPS[currentStepIndex + 1].id);
      }
    },
    [currentStep, currentStepIndex, profile, aiConfig, completeStep, setStep, setError, clearErrors]
  );

  const handleBack = useCallback(() => {
    if (currentStepIndex > 0) {
      setStep(STEPS[currentStepIndex - 1].id);
    }
  }, [currentStepIndex, setStep]);

  const handleLaunch = async () => {
    try {
      setSubmitting(true);
      clearErrors();

      const payload = {
        profile,
        channels: channels.filter((c) => c.enabled),
        aiConfig,
        knowledgeBase,
      };

      await apiClient.post("/api/v1/onboarding/complete", payload);

      setShowConfetti(true);
      setTimeout(() => {
        router.push("/dashboard");
      }, 2000);
    } catch (error) {
      setError("launch", error instanceof Error ? error.message : "Failed to launch");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 text-white">
      {/* Confetti animation */}
      {showConfetti && <Confetti />}

      {/* Background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500 opacity-10 blur-3xl rounded-full" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-500 opacity-10 blur-3xl rounded-full" />
      </div>

      {/* Header */}
      <div className="relative z-10 border-b border-slate-700/50 backdrop-blur-xl bg-slate-900/30">
        <div className="max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-blue-500 rounded-lg flex items-center justify-center">
              <Sparkles className="w-6 h-6" />
            </div>
            <h1 className="text-2xl font-bold">Partython.ai</h1>
          </div>
          <p className="text-slate-400 text-sm">Step {currentStepIndex + 1} of {STEPS.length}</p>
        </div>
      </div>

      {/* Step Indicator */}
      <div className="relative z-10 max-w-7xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-12">
          {STEPS.map((step, index) => {
            const isCompleted = index < currentStepIndex;
            const isCurrent = step.id === currentStep;
            const Icon = step.icon;

            return (
              <div key={step.id} className="flex items-center flex-1">
                <motion.div
                  initial={false}
                  animate={{
                    scale: isCurrent ? 1.1 : 1,
                  }}
                  className={`flex items-center justify-center w-12 h-12 rounded-full border-2 transition-all ${
                    isCompleted || isCurrent
                      ? "bg-purple-600 border-purple-400"
                      : "bg-slate-700 border-slate-600"
                  }`}
                >
                  {isCompleted ? (
                    <Check className="w-6 h-6" />
                  ) : (
                    <Icon className="w-6 h-6" />
                  )}
                </motion.div>

                <div className="ml-3 hidden sm:block">
                  <p className={`text-sm font-medium ${isCurrent ? "text-purple-400" : "text-slate-400"}`}>
                    {step.label}
                  </p>
                </div>

                {index < STEPS.length - 1 && (
                  <motion.div
                    initial={false}
                    animate={{
                      scaleX: isCompleted ? 1 : 0,
                    }}
                    className={`h-1 flex-1 mx-2 origin-left rounded-full ${
                      isCompleted ? "bg-purple-600" : "bg-slate-700"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Content */}
      <div className="relative z-10 max-w-4xl mx-auto px-6 pb-12">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            {currentStep === "business_setup" && (
              <Step1BusinessSetup
                profile={profile}
                updateProfile={updateProfile}
                errors={errors}
                setError={setError}
              />
            )}

            {currentStep === "channels" && (
              <Step2Channels />
            )}

            {currentStep === "ai_config" && (
              <Step3AIConfiguration
                aiConfig={aiConfig}
                updateAIConfig={updateAIConfig}
                errors={errors}
                setError={setError}
              />
            )}

            {currentStep === "knowledge_base" && (
              <Step4KnowledgeBase
                items={knowledgeBase}
                addItem={addKnowledgeBaseItem}
                updateItem={updateKnowledgeBaseItem}
                removeItem={removeKnowledgeBaseItem}
              />
            )}

            {currentStep === "launch" && (
              <Step5Launch
                profile={profile}
                channels={channels}
                aiConfig={aiConfig}
                knowledgeBase={knowledgeBase}
              />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Error message */}
        {errors.launch && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 p-4 bg-red-500/20 border border-red-500/30 rounded-lg flex gap-3"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-400" />
            <p className="text-red-300">{errors.launch}</p>
          </motion.div>
        )}

        {/* Navigation buttons */}
        <div className="flex items-center justify-between mt-12 gap-4">
          <button
            onClick={handleBack}
            disabled={currentStepIndex === 0}
            className="flex items-center gap-2 px-6 py-3 rounded-lg border border-slate-600 hover:border-slate-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-5 h-5" />
            Back
          </button>

          {currentStep === "launch" ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleLaunch}
              disabled={isSubmitting}
              className="flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-purple-600 to-blue-600 rounded-lg hover:from-purple-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Launching...
                </>
              ) : (
                <>
                  <Rocket className="w-5 h-5" />
                  Launch Your AI Assistant
                </>
              )}
            </motion.button>
          ) : (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => handleNext(false)}
              className="flex items-center gap-2 px-8 py-3 bg-gradient-to-r from-purple-600 to-blue-600 rounded-lg hover:from-purple-500 hover:to-blue-500 transition-all font-medium"
            >
              Next
              <ChevronRight className="w-5 h-5" />
            </motion.button>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// STEP 1: BUSINESS SETUP
// ============================================================================

interface Step1Props {
  profile: any;
  updateProfile: (data: any) => void;
  errors: Record<string, string>;
  setError: (field: string, msg: string) => void;
}

function Step1BusinessSetup({ profile, updateProfile, errors, setError }: Step1Props) {
  const handleLogoUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const formData = new FormData();
      formData.append("file", file);

      // Mock upload - replace with actual API call
      const url = URL.createObjectURL(file);
      updateProfile({ logo_url: url });
    } catch (error) {
      setError("logo_upload", "Failed to upload logo");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Setup Your Business Profile</h2>
        <p className="text-slate-400">Tell us about your business to personalize your AI assistant</p>
      </div>

      {/* Logo Upload */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-8">
        <label className="block mb-4">
          <span className="text-sm font-medium mb-3 block">Business Logo</span>
          <motion.div
            whileHover={{ borderColor: "#a78bfa" }}
            className="relative border-2 border-dashed border-slate-600 rounded-lg p-8 text-center transition-colors cursor-pointer hover:bg-slate-700/30"
          >
            <input
              type="file"
              accept="image/*"
              onChange={handleLogoUpload}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />
            {profile.logo_url ? (
              <img src={profile.logo_url} alt="Logo" className="w-24 h-24 mx-auto object-cover rounded-lg" />
            ) : (
              <div className="py-4">
                <Upload className="w-8 h-8 mx-auto text-slate-400 mb-2" />
                <p className="text-slate-400">Click or drag to upload your logo</p>
              </div>
            )}
          </motion.div>
        </label>
      </div>

      {/* Business Name */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Business Name <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={profile.company_name}
          onChange={(e) => updateProfile({ company_name: e.target.value })}
          placeholder="Enter your business name"
          className={`w-full px-4 py-3 bg-slate-700 border rounded-lg focus:outline-none focus:ring-2 transition-all ${
            errors.company_name ? "border-red-500 focus:ring-red-500" : "border-slate-600 focus:ring-purple-500"
          }`}
        />
        {errors.company_name && <p className="text-red-400 text-sm mt-1">{errors.company_name}</p>}
      </div>

      {/* Industry & Timezone Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Industry */}
        <div>
          <label className="block text-sm font-medium mb-2">
            Industry <span className="text-red-400">*</span>
          </label>
          <select
            value={profile.industry}
            onChange={(e) => updateProfile({ industry: e.target.value })}
            className={`w-full px-4 py-3 bg-slate-700 border rounded-lg focus:outline-none focus:ring-2 transition-all ${
              errors.industry ? "border-red-500 focus:ring-red-500" : "border-slate-600 focus:ring-purple-500"
            }`}
          >
            <option value="">Select an industry</option>
            {INDUSTRIES.map((ind) => (
              <option key={ind.value} value={ind.value}>
                {ind.label}
              </option>
            ))}
          </select>
          {errors.industry && <p className="text-red-400 text-sm mt-1">{errors.industry}</p>}
        </div>

        {/* Timezone */}
        <div>
          <label className="block text-sm font-medium mb-2">
            Timezone <span className="text-red-400">*</span>
          </label>
          <select
            value={profile.timezone}
            onChange={(e) => updateProfile({ timezone: e.target.value })}
            className={`w-full px-4 py-3 bg-slate-700 border rounded-lg focus:outline-none focus:ring-2 transition-all ${
              errors.timezone ? "border-red-500 focus:ring-red-500" : "border-slate-600 focus:ring-purple-500"
            }`}
          >
            <option value="">Select a timezone</option>
            {TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
          {errors.timezone && <p className="text-red-400 text-sm mt-1">{errors.timezone}</p>}
        </div>
      </div>

      {/* Language */}
      <div>
        <label className="block text-sm font-medium mb-2">Preferred Language</label>
        <select
          value={profile.language}
          onChange={(e) => updateProfile({ language: e.target.value })}
          className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all"
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.value} value={lang.value}>
              {lang.label}
            </option>
          ))}
        </select>
      </div>

      {/* Website URL */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Business Website URL <span className="text-red-400">*</span>
        </label>
        <input
          type="url"
          value={profile.website}
          onChange={(e) => updateProfile({ website: e.target.value })}
          placeholder="https://example.com"
          className={`w-full px-4 py-3 bg-slate-700 border rounded-lg focus:outline-none focus:ring-2 transition-all ${
            errors.website ? "border-red-500 focus:ring-red-500" : "border-slate-600 focus:ring-purple-500"
          }`}
        />
        {errors.website && <p className="text-red-400 text-sm mt-1">{errors.website}</p>}
      </div>
    </div>
  );
}

// ============================================================================
// STEP 2: CONNECT CHANNELS
// ============================================================================

function Step2Channels() {
  const { channels, updateChannel, removeChannel, addChannel } = useOnboardingStore();

  const handleConnect = (channelId: string) => {
    const existingIndex = channels.findIndex((c) => c.channel_type === channelId);

    if (existingIndex >= 0) {
      updateChannel(existingIndex, { enabled: true });
    } else {
      addChannel({
        channel_type: channelId,
        enabled: true,
        credentials: {},
        status: "not_started",
      });
    }
  };

  const handleSkip = (channelId: string) => {
    const existingIndex = channels.findIndex((c) => c.channel_type === channelId);
    if (existingIndex >= 0) {
      removeChannel(existingIndex);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Connect Your Channels</h2>
        <p className="text-slate-400">Choose which communication channels to enable for your AI assistant</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {CHANNELS_AVAILABLE.map((channel) => {
          const Icon = channel.icon;
          const isConnected = channels.some(
            (c) => c.channel_type === channel.id && c.enabled
          );

          return (
            <motion.div
              key={channel.id}
              whileHover={{ y: -4 }}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-6 transition-all hover:border-slate-600"
            >
              <div className="flex items-start justify-between mb-4">
                <div className={`w-12 h-12 rounded-lg ${channel.color} flex items-center justify-center flex-shrink-0`}>
                  <Icon className="w-6 h-6 text-white" />
                </div>
                {isConnected && (
                  <div className="flex items-center gap-1 px-3 py-1 bg-green-500/20 border border-green-500/30 rounded-full text-green-400 text-xs font-medium">
                    <Check className="w-3 h-3" />
                    Connected
                  </div>
                )}
              </div>

              <h3 className="font-semibold mb-1">{channel.name}</h3>
              <p className="text-slate-400 text-sm mb-4">{channel.description}</p>

              <div className="flex gap-2">
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => handleConnect(channel.id)}
                  className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm font-medium transition-colors"
                >
                  {isConnected ? "Connected" : "Connect"}
                </motion.button>
                {isConnected && (
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleSkip(channel.id)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors"
                  >
                    Remove
                  </motion.button>
                )}
                {!isConnected && (
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleSkip(channel.id)}
                    className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors"
                  >
                    Skip
                  </motion.button>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>

      <div className="bg-slate-800/30 border border-slate-700 rounded-xl p-6">
        <div className="flex gap-3">
          <Zap className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm mb-1">You can always add more channels later</p>
            <p className="text-slate-400 text-sm">Start with your most important channels and expand as needed</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// STEP 3: AI CONFIGURATION
// ============================================================================

interface Step3Props {
  aiConfig: any;
  updateAIConfig: (data: any) => void;
  errors: Record<string, string>;
  setError: (field: string, msg: string) => void;
}

function Step3AIConfiguration({ aiConfig, updateAIConfig, errors, setError }: Step3Props) {
  const [selectedPersonality, setSelectedPersonality] = useState(aiConfig.tone_preset || "professional");

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Configure Your AI Assistant</h2>
        <p className="text-slate-400">Customize personality, language, and response settings</p>
      </div>

      {/* AI Persona Name */}
      <div>
        <label className="block text-sm font-medium mb-2">
          AI Assistant Name <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={aiConfig.ai_persona_name}
          onChange={(e) => updateAIConfig({ ai_persona_name: e.target.value })}
          placeholder="e.g., Alex, Maya, or Assistant Pro"
          className={`w-full px-4 py-3 bg-slate-700 border rounded-lg focus:outline-none focus:ring-2 transition-all ${
            errors.ai_persona_name ? "border-red-500 focus:ring-red-500" : "border-slate-600 focus:ring-purple-500"
          }`}
        />
        {errors.ai_persona_name && <p className="text-red-400 text-sm mt-1">{errors.ai_persona_name}</p>}
      </div>

      {/* Personality Selection */}
      <div>
        <label className="block text-sm font-medium mb-4">Choose Personality</label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {AI_PERSONALITIES.map((personality) => (
            <motion.button
              key={personality.id}
              whileHover={{ scale: 1.02 }}
              onClick={() => {
                setSelectedPersonality(personality.id);
                updateAIConfig({ tone_preset: personality.id });
              }}
              className={`text-left p-6 rounded-lg border-2 transition-all ${
                selectedPersonality === personality.id
                  ? "border-purple-500 bg-purple-500/10"
                  : "border-slate-600 bg-slate-800/30 hover:border-slate-500"
              }`}
            >
              <h3 className="font-semibold mb-2">{personality.label}</h3>
              <p className="text-sm text-slate-400 mb-3">{personality.description}</p>
              <div className="space-y-1">
                {personality.examples.map((example, i) => (
                  <p key={i} className="text-xs text-slate-500 italic">
                    "{example}"
                  </p>
                ))}
              </div>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Response Language */}
      <div>
        <label className="block text-sm font-medium mb-2">Response Language</label>
        <select
          value={aiConfig.response_language}
          onChange={(e) => updateAIConfig({ response_language: e.target.value })}
          className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all"
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.value} value={lang.value}>
              {lang.label}
            </option>
          ))}
        </select>
      </div>

      {/* Auto-Reply Toggle */}
      <div className="flex items-center justify-between p-4 bg-slate-800/30 border border-slate-700 rounded-lg">
        <div className="flex items-center gap-3">
          <Send className="w-5 h-5 text-blue-400" />
          <div>
            <p className="font-medium text-sm">Enable Auto-Replies</p>
            <p className="text-slate-400 text-xs">Respond immediately to messages</p>
          </div>
        </div>
        <button
          onClick={() => updateAIConfig({ auto_reply_enabled: !aiConfig.auto_reply_enabled })}
          className={`w-12 h-6 rounded-full transition-all ${
            aiConfig.auto_reply_enabled ? "bg-green-500" : "bg-slate-600"
          }`}
        >
          <motion.div
            initial={false}
            animate={{ x: aiConfig.auto_reply_enabled ? 24 : 2 }}
            className="w-5 h-5 bg-white rounded-full"
          />
        </button>
      </div>

      {/* Confidence Threshold */}
      <div>
        <label className="block text-sm font-medium mb-2">
          <div className="flex items-center gap-2">
            <Gauge className="w-4 h-4" />
            AI Confidence Threshold
          </div>
        </label>
        <p className="text-slate-400 text-sm mb-3">Lower values = more responses, Higher values = more cautious</p>
        <input
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={aiConfig.confidence_threshold}
          onChange={(e) => updateAIConfig({ confidence_threshold: parseFloat(e.target.value) })}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-slate-400 mt-2">
          <span>Liberal (0.3)</span>
          <span className="font-medium text-slate-300">{(aiConfig.confidence_threshold * 100).toFixed(0)}%</span>
          <span>Conservative (1.0)</span>
        </div>
      </div>

      {/* Custom Instructions */}
      <div>
        <label className="block text-sm font-medium mb-2">Custom Instructions (Optional)</label>
        <textarea
          value={aiConfig.custom_instructions}
          onChange={(e) => updateAIConfig({ custom_instructions: e.target.value })}
          placeholder="Add special instructions to guide AI behavior..."
          rows={4}
          className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all resize-none"
        />
      </div>
    </div>
  );
}

// ============================================================================
// STEP 4: KNOWLEDGE BASE
// ============================================================================

interface Step4Props {
  items: any[];
  addItem: (item: any) => void;
  updateItem: (id: string, data: any) => void;
  removeItem: (id: string) => void;
}

function Step4KnowledgeBase({ items, addItem, updateItem, removeItem }: Step4Props) {
  const [urlInput, setUrlInput] = useState("");
  const [faqQuestion, setFaqQuestion] = useState("");
  const [faqAnswer, setFaqAnswer] = useState("");

  const handleDocumentUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const item = {
      type: "document",
      title: file.name,
      status: "processing",
    };
    addItem(item);

    // Simulate upload
    setTimeout(() => {
      const lastItem = items[items.length - 1];
      if (lastItem?.id) {
        updateItem(lastItem.id, { status: "completed" });
      }
    }, 2000);
  };

  const handleAddURL = () => {
    if (urlInput.trim()) {
      addItem({
        type: "url",
        title: urlInput,
        url: urlInput,
        status: "processing",
      });
      setUrlInput("");

      // Simulate crawling
      setTimeout(() => {
        const lastItem = items[items.length - 1];
        if (lastItem?.id) {
          updateItem(lastItem.id, { status: "completed" });
        }
      }, 3000);
    }
  };

  const handleAddFAQ = () => {
    if (faqQuestion.trim() && faqAnswer.trim()) {
      addItem({
        type: "faq",
        title: faqQuestion,
        content: faqAnswer,
        status: "completed",
      });
      setFaqQuestion("");
      setFaqAnswer("");
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Build Your Knowledge Base</h2>
        <p className="text-slate-400">Upload documents, add URLs, and FAQs to train your AI assistant</p>
      </div>

      {/* Document Upload */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-8">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Upload className="w-5 h-5" />
          Upload Documents
        </h3>
        <motion.div
          whileHover={{ borderColor: "#a78bfa" }}
          className="relative border-2 border-dashed border-slate-600 rounded-lg p-8 text-center transition-colors cursor-pointer hover:bg-slate-700/30"
        >
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={handleDocumentUpload}
            className="absolute inset-0 opacity-0 cursor-pointer"
            multiple
          />
          <div className="py-4">
            <FileText className="w-8 h-8 mx-auto text-slate-400 mb-2" />
            <p className="text-slate-400">Click or drag to upload (PDF, DOCX, TXT)</p>
          </div>
        </motion.div>
      </div>

      {/* URL Crawling */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Globe className="w-5 h-5" />
          Crawl Website
        </h3>
        <div className="flex gap-2">
          <input
            type="url"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="https://example.com"
            className="flex-1 px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleAddURL}
            className="px-6 py-3 bg-purple-600 hover:bg-purple-500 rounded-lg font-medium transition-colors"
          >
            <Plus className="w-5 h-5" />
          </motion.button>
        </div>
      </div>

      {/* FAQ Entry */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <MessageSquare className="w-5 h-5" />
          Add FAQ
        </h3>
        <div className="space-y-3 mb-4">
          <input
            type="text"
            value={faqQuestion}
            onChange={(e) => setFaqQuestion(e.target.value)}
            placeholder="Question"
            className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <textarea
            value={faqAnswer}
            onChange={(e) => setFaqAnswer(e.target.value)}
            placeholder="Answer"
            rows={3}
            className="w-full px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
          />
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleAddFAQ}
            className="w-full px-4 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-colors"
          >
            Add FAQ
          </motion.button>
        </div>
      </div>

      {/* Items List */}
      {items.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-700 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">Knowledge Base Items ({items.length})</h3>
          <div className="space-y-3">
            {items.map((item) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="flex items-center justify-between p-4 bg-slate-700/50 rounded-lg"
              >
                <div className="flex items-center gap-3 flex-1">
                  {item.status === "completed" ? (
                    <Check className="w-5 h-5 text-green-400" />
                  ) : item.status === "processing" ? (
                    <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-red-400" />
                  )}
                  <div className="flex-1">
                    <p className="font-medium text-sm">{item.title}</p>
                    <p className="text-xs text-slate-400">
                      {item.type === "document"
                        ? "Document"
                        : item.type === "url"
                          ? "Website"
                          : "FAQ"}
                    </p>
                  </div>
                </div>
                <motion.button
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={() => removeItem(item.id || "")}
                  className="p-2 hover:bg-red-500/20 rounded-lg text-red-400 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </motion.button>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-slate-800/30 border border-slate-700 rounded-xl p-6">
        <div className="flex gap-3">
          <Brain className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-sm mb-1">Train your AI continuously</p>
            <p className="text-slate-400 text-sm">You can add more content anytime after launch</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// STEP 5: LAUNCH
// ============================================================================

interface Step5Props {
  profile: any;
  channels: any[];
  aiConfig: any;
  knowledgeBase: any[];
}

function Step5Launch({ profile, channels, aiConfig, knowledgeBase }: Step5Props) {
  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Review & Launch</h2>
        <p className="text-slate-400">Everything looks great! Time to bring your AI assistant to life</p>
      </div>

      {/* Configuration Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Business Profile */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-6"
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-blue-400" />
            Business Setup
          </h3>
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-slate-400">Company:</span> <span className="font-medium">{profile.company_name}</span>
            </p>
            <p>
              <span className="text-slate-400">Industry:</span> <span className="font-medium capitalize">{profile.industry}</span>
            </p>
            <p>
              <span className="text-slate-400">Timezone:</span> <span className="font-medium">{profile.timezone}</span>
            </p>
            <p>
              <span className="text-slate-400">Language:</span> <span className="font-medium">{profile.language}</span>
            </p>
          </div>
        </motion.div>

        {/* AI Configuration */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-6"
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-400" />
            AI Configuration
          </h3>
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-slate-400">Name:</span> <span className="font-medium">{aiConfig.ai_persona_name}</span>
            </p>
            <p>
              <span className="text-slate-400">Personality:</span> <span className="font-medium capitalize">{aiConfig.tone_preset}</span>
            </p>
            <p>
              <span className="text-slate-400">Auto-Reply:</span> <span className="font-medium">{aiConfig.auto_reply_enabled ? "Enabled" : "Disabled"}</span>
            </p>
            <p>
              <span className="text-slate-400">Confidence:</span> <span className="font-medium">{(aiConfig.confidence_threshold * 100).toFixed(0)}%</span>
            </p>
          </div>
        </motion.div>

        {/* Channels */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-6"
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-green-400" />
            Connected Channels ({channels.filter((c) => c.enabled).length})
          </h3>
          <div className="space-y-2 text-sm">
            {channels.filter((c) => c.enabled).length > 0 ? (
              channels
                .filter((c) => c.enabled)
                .map((channel) => (
                  <div key={channel.channel_type} className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="font-medium capitalize">{channel.channel_type}</span>
                  </div>
                ))
            ) : (
              <p className="text-slate-400">No channels connected</p>
            )}
          </div>
        </motion.div>

        {/* Knowledge Base */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-6"
        >
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5 text-orange-400" />
            Knowledge Base ({knowledgeBase.length} items)
          </h3>
          <div className="space-y-2 text-sm">
            {knowledgeBase.length > 0 ? (
              knowledgeBase.slice(0, 3).map((item) => (
                <p key={item.id} className="text-slate-300 truncate">
                  {item.title}
                </p>
              ))
            ) : (
              <p className="text-slate-400">No knowledge base items</p>
            )}
            {knowledgeBase.length > 3 && (
              <p className="text-slate-500 text-xs">+{knowledgeBase.length - 3} more</p>
            )}
          </div>
        </motion.div>
      </div>

      {/* Test Conversation Preview */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="bg-gradient-to-br from-slate-800/50 to-slate-700/30 border border-slate-700 rounded-xl p-8"
      >
        <h3 className="font-semibold mb-6 flex items-center gap-2">
          <MessageCircle className="w-5 h-5" />
          Test Conversation Preview
        </h3>

        <div className="bg-slate-900 rounded-lg p-4 h-64 overflow-y-auto space-y-4 mb-4">
          <div className="flex justify-start">
            <div className="bg-slate-700 rounded-lg px-4 py-2 max-w-xs">
              <p className="text-sm">
                Hi! I'm {aiConfig.ai_persona_name || "your AI assistant"}. How can I help you today?
              </p>
            </div>
          </div>
          <div className="flex justify-end">
            <div className="bg-purple-600 rounded-lg px-4 py-2 max-w-xs">
              <p className="text-sm">What's your return policy?</p>
            </div>
          </div>
          <div className="flex justify-start">
            <div className="bg-slate-700 rounded-lg px-4 py-2 max-w-xs">
              <p className="text-sm">Great question! We offer 30-day returns on all products.</p>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Try a test message..."
            className="flex-1 px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="px-4 py-3 bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors"
          >
            <Send className="w-5 h-5" />
          </motion.button>
        </div>
      </motion.div>

      {/* Final CTA */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        className="bg-gradient-to-r from-purple-600/20 to-blue-600/20 border border-purple-500/30 rounded-xl p-8 text-center"
      >
        <Sparkles className="w-12 h-12 mx-auto mb-4 text-purple-400" />
        <h3 className="text-xl font-semibold mb-2">Ready to Launch?</h3>
        <p className="text-slate-400 mb-4">
          Your AI assistant is fully configured and ready to serve your customers across all channels.
        </p>
        <p className="text-sm text-slate-500">Click the Launch button below to go live immediately</p>
      </motion.div>
    </div>
  );
}

// ============================================================================
// CONFETTI COMPONENT
// ============================================================================

function Confetti() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-50">
      {Array.from({ length: 50 }).map((_, i) => (
        <motion.div
          key={i}
          initial={{
            x: Math.random() * window.innerWidth,
            y: -10,
            opacity: 1,
            rotate: Math.random() * 360,
          }}
          animate={{
            y: window.innerHeight + 10,
            opacity: 0,
            rotate: Math.random() * 720,
          }}
          transition={{
            duration: 2 + Math.random() * 1,
            ease: "easeIn",
          }}
          className={`fixed w-2 h-2 rounded-full ${
            ["bg-purple-400", "bg-blue-400", "bg-pink-400", "bg-yellow-400"][Math.floor(Math.random() * 4)]
          }`}
        />
      ))}
    </div>
  );
}
