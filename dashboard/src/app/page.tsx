'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion'
import { ArrowRight, ArrowUpRight, CheckCircle, Play, ChevronRight, Zap, Shield, Globe, BarChart3, Clock, Users, Sparkles, Star, Menu, X } from 'lucide-react'

/* ========================================================================
   PRIYA GLOBAL — Landing Page
   International SaaS quality. Asymmetric layouts. Strong typography.
   ======================================================================== */

// ─── Channel brand data ─────────────────────────────────────────────────────
const CHANNELS = [
  { name: 'WhatsApp', color: '#25D366', path: 'M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z' },
  { name: 'Email', color: '#EA4335', path: 'M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z' },
  { name: 'Voice', color: '#5B5FC7', path: 'M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z' },
  { name: 'Instagram', color: '#E1306C', path: 'M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z' },
  { name: 'Facebook', color: '#1877F2', path: 'M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z' },
  { name: 'Web Chat', color: '#6366f1', path: 'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z' },
]

const METRICS = [
  { value: '44,000+', label: 'Orders Processed', sub: 'and growing daily' },
  { value: '6', label: 'Channels Supported', sub: 'unified inbox' },
  { value: '85%', label: 'Auto-resolved', sub: 'without handoff' },
  { value: '<3s', label: 'Avg Reply Time', sub: 'across all channels' },
]

const INTEGRATIONS = [
  { name: 'Shopify', desc: 'Sync orders, products & customers in real-time' },
  { name: 'WhatsApp Business', desc: 'Official API with template messaging' },
  { name: 'Meta / Instagram', desc: 'DMs, comments & story replies' },
  { name: 'Google Workspace', desc: 'Gmail, Calendar & Sheets integration' },
  { name: 'Exotel', desc: 'Voice calls, IVR & call recording' },
  { name: 'Twilio', desc: 'SMS, Voice & programmable messaging' },
  { name: 'Cloudflare', desc: 'CDN, DNS & tunnel infrastructure' },
  { name: 'ElevenLabs', desc: 'AI voice cloning & text-to-speech' },
]

const FEATURES = [
  {
    icon: Globe,
    title: 'Omnichannel Inbox',
    desc: 'WhatsApp, Email, Voice, Instagram, Facebook, and Web Chat — one unified thread per customer. No tab-switching, no context lost.',
    tag: 'Core',
  },
  {
    icon: Sparkles,
    title: 'AI That Sells',
    desc: 'Trained on your product catalog, pricing, and brand voice. Partython.ai qualifies leads, answers objections, and nudges prospects to close.',
    tag: 'AI',
  },
  {
    icon: BarChart3,
    title: 'Revenue Analytics',
    desc: 'Track conversations-to-revenue attribution per channel. See which channels convert, where leads drop off, and where to double down.',
    tag: 'Analytics',
  },
  {
    icon: Users,
    title: 'Smart Handoffs',
    desc: 'When the AI hits its limit, it hands off to a human with full conversation context, lead score, and suggested next action.',
    tag: 'Workflow',
  },
  {
    icon: Shield,
    title: 'Enterprise Security',
    desc: 'SOC 2 Type II compliant. Data encrypted at rest and in transit. Role-based access, SSO, audit logs, and data residency controls.',
    tag: 'Security',
  },
  {
    icon: Zap,
    title: '5-Minute Setup',
    desc: 'Connect your channels, upload your knowledge base, configure your AI persona. Go live in under five minutes — no engineering needed.',
    tag: 'Setup',
  },
]

const CASE_STUDIES = [
  {
    industry: 'E-Commerce',
    challenge: 'High cart abandonment and slow response to customer queries across WhatsApp and Instagram',
    result: 'Automated follow-ups recovered 23% of abandoned carts. Response time dropped from hours to seconds.',
    metric: '23% cart recovery',
    channels: ['WhatsApp', 'Instagram'],
  },
  {
    industry: 'D2C Retail',
    challenge: 'Managing personalized orders across 6 channels with a small team during peak season',
    result: 'AI handled 85% of conversations autonomously. Team focused on fulfillment instead of answering queries.',
    metric: '85% automation rate',
    channels: ['WhatsApp', 'Voice', 'Email'],
  },
  {
    industry: 'SaaS',
    challenge: 'Lead qualification was manual and inconsistent. Sales team spent 60% of time on unqualified leads.',
    result: 'AI pre-qualified leads before handoff. Sales conversion rate improved by 3x with better lead scoring.',
    metric: '3x conversion rate',
    channels: ['Web Chat', 'Email'],
  },
]

const PLANS = [
  {
    name: 'Starter',
    price: '$49',
    period: '/mo',
    desc: 'For solo founders testing AI sales',
    features: ['500 conversations/mo', '2 channels', 'Basic analytics', 'Email support', 'Knowledge base (5 docs)'],
    cta: 'Start Free Trial',
    highlight: false,
  },
  {
    name: 'Growth',
    price: '$149',
    period: '/mo',
    desc: 'For teams ready to scale',
    features: ['5,000 conversations/mo', 'All 6 channels', 'Revenue attribution', '3 team members', 'Custom AI persona', 'Priority support'],
    cta: 'Start Free Trial',
    highlight: true,
    badge: 'Most Popular',
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    desc: 'For large operations',
    features: ['Unlimited conversations', 'All channels + API', 'Custom integrations', 'Unlimited team members', 'Dedicated CSM', 'SSO & audit logs', 'SLA guarantee'],
    cta: 'Talk to Sales',
    highlight: false,
  },
]

// ─── Animations ─────────────────────────────────────────────────────────────
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.1, ease: [0.25, 0.4, 0.25, 1] },
  }),
}

const stagger = {
  visible: { transition: { staggerChildren: 0.08 } },
}

// ─── Navbar ─────────────────────────────────────────────────────────────────
function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${scrolled ? 'glass shadow-sm' : 'bg-transparent'}`}>
      <div className="section-container flex items-center justify-between h-16 md:h-20">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 no-underline">
          <div className="w-9 h-9 rounded-xl bg-primary-600 flex items-center justify-center text-white font-bold text-sm tracking-wide">
            P
          </div>
          <span className="text-lg font-bold text-neutral-900 dark:text-white tracking-tight">
            Partython<span className="text-primary-600">.ai</span>
          </span>
        </Link>

        {/* Desktop Nav */}
        <div className="hidden md:flex items-center gap-8">
          <a href="#features" className="text-sm font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white no-underline smooth">Features</a>
          <a href="#pricing" className="text-sm font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white no-underline smooth">Pricing</a>
          <a href="#testimonials" className="text-sm font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white no-underline smooth">Case Studies</a>
          <a href="#about" className="text-sm font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white no-underline smooth">About</a>
        </div>

        <div className="hidden md:flex items-center gap-3">
          <Link href="/login" className="text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-white no-underline px-4 py-2 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 smooth">
            Sign in
          </Link>
          <Link href="/register" className="text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 px-5 py-2.5 rounded-lg no-underline smooth shadow-sm shadow-primary-600/25">
            Get Started
          </Link>
        </div>

        {/* Mobile menu toggle */}
        <button onClick={() => setMobileOpen(!mobileOpen)} className="md:hidden p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg">
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden glass border-t border-neutral-200/50 dark:border-neutral-700/50"
          >
            <div className="section-container py-4 space-y-3">
              <a href="#features" onClick={() => setMobileOpen(false)} className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 no-underline py-2">Features</a>
              <a href="#pricing" onClick={() => setMobileOpen(false)} className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 no-underline py-2">Pricing</a>
              <a href="#testimonials" onClick={() => setMobileOpen(false)} className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 no-underline py-2">Case Studies</a>
              <a href="#about" onClick={() => setMobileOpen(false)} className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 no-underline py-2">About</a>
              <div className="pt-3 flex flex-col gap-2">
                <Link href="/login" className="text-center text-sm font-medium text-neutral-700 dark:text-neutral-300 no-underline py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700">Sign in</Link>
                <Link href="/register" className="text-center text-sm font-semibold text-white bg-primary-600 no-underline py-2.5 rounded-lg">Get Started</Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}

// ─── Channel Icon ───────────────────────────────────────────────────────────
function ChannelIcon({ channel, size = 40 }: { channel: typeof CHANNELS[0]; size?: number }) {
  return (
    <div
      className="flex items-center justify-center rounded-xl smooth group-hover:scale-105"
      style={{ width: size, height: size, backgroundColor: channel.color }}
    >
      <svg viewBox="0 0 24 24" fill="white" style={{ width: size * 0.5, height: size * 0.5 }}>
        <path d={channel.path} />
      </svg>
    </div>
  )
}

// ─── Main Page ──────────────────────────────────────────────────────────────
export default function LandingPage() {
  const { scrollYProgress } = useScroll()
  const heroY = useTransform(scrollYProgress, [0, 0.3], [0, -60])

  return (
    <div className="min-h-screen bg-white dark:bg-neutral-950 overflow-hidden">
      <Navbar />

      {/* ════════════════════════════════════════════════════════════════════
          HERO — Left-aligned, asymmetric, confident
          ════════════════════════════════════════════════════════════════════ */}
      <section className="relative pt-28 md:pt-36 pb-20 md:pb-32">
        {/* Background grid */}
        <div className="absolute inset-0 dot-grid opacity-50" />
        <div className="absolute top-20 right-0 w-[600px] h-[600px] bg-primary-500/8 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-accent-500/6 rounded-full blur-3xl pointer-events-none" />

        <div className="section-container relative">
          <div className="grid lg:grid-cols-12 gap-12 lg:gap-8 items-center">
            {/* Left — Copy */}
            <motion.div
              className="lg:col-span-7"
              style={{ y: heroY }}
              initial="hidden"
              animate="visible"
              variants={stagger}
            >
              {/* Pill badge */}
              <motion.div variants={fadeUp} custom={0} className="mb-6">
                <span className="inline-flex items-center gap-2 bg-primary-50 dark:bg-primary-950/40 text-primary-700 dark:text-primary-300 text-xs font-semibold px-4 py-1.5 rounded-full border border-primary-200/60 dark:border-primary-800/40">
                  <span className="w-1.5 h-1.5 bg-primary-500 rounded-full animate-pulse" />
                  Now with Voice AI &mdash; calls that convert
                </span>
              </motion.div>

              <motion.h1 variants={fadeUp} custom={1} className="text-balance">
                Your AI Sales Team,{' '}
                <span className="gradient-text">Always On</span>
              </motion.h1>

              <motion.p variants={fadeUp} custom={2} className="mt-6 text-lg md:text-xl text-neutral-500 dark:text-neutral-400 leading-relaxed max-w-xl text-pretty">
                Partython.ai handles customer conversations across WhatsApp, Email, Voice, Instagram, Facebook, and Web Chat &mdash; 24 hours a day, 7 days a week. Your customers get instant answers. You get more revenue.
              </motion.p>

              {/* CTA row */}
              <motion.div variants={fadeUp} custom={3} className="mt-8 flex flex-col sm:flex-row gap-3">
                <Link
                  href="/register"
                  className="inline-flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm px-7 py-3.5 rounded-xl no-underline smooth shadow-lg shadow-primary-600/25 hover:shadow-xl hover:shadow-primary-600/30"
                >
                  Start Free Trial
                  <ArrowRight size={16} />
                </Link>
                <button className="inline-flex items-center justify-center gap-2 text-neutral-700 dark:text-neutral-300 font-medium text-sm px-6 py-3.5 rounded-xl border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800 smooth">
                  <Play size={16} className="text-primary-600" />
                  Watch Demo
                </button>
              </motion.div>

              <motion.p variants={fadeUp} custom={4} className="mt-4 text-xs text-neutral-400 dark:text-neutral-500">
                No credit card required &middot; 30-day free trial &middot; Cancel anytime
              </motion.p>

              {/* Channel strip */}
              <motion.div variants={fadeUp} custom={5} className="mt-10 flex items-center gap-3">
                <span className="text-xs font-medium text-neutral-400 dark:text-neutral-500 uppercase tracking-wider mr-1">Channels</span>
                <div className="flex items-center gap-2">
                  {CHANNELS.map((ch) => (
                    <div key={ch.name} className="group" title={ch.name}>
                      <ChannelIcon channel={ch} size={34} />
                    </div>
                  ))}
                </div>
              </motion.div>
            </motion.div>

            {/* Right — Metrics card / visual */}
            <motion.div
              className="lg:col-span-5"
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: 0.4, ease: [0.25, 0.4, 0.25, 1] }}
            >
              <div className="relative">
                {/* Glow */}
                <div className="absolute -inset-4 bg-gradient-to-br from-primary-500/20 to-accent-500/20 rounded-3xl blur-2xl" />

                {/* Card */}
                <div className="relative bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200/80 dark:border-neutral-800 shadow-2xl shadow-neutral-900/8 dark:shadow-black/30 overflow-hidden">
                  {/* Top bar */}
                  <div className="px-5 py-3.5 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-red-400" />
                      <div className="w-3 h-3 rounded-full bg-yellow-400" />
                      <div className="w-3 h-3 rounded-full bg-green-400" />
                    </div>
                    <span className="text-[11px] font-medium text-neutral-400">Partython Dashboard</span>
                  </div>

                  {/* Mock dashboard content */}
                  <div className="p-5 space-y-4">
                    {/* Stats row */}
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label: 'Active Chats', value: '127', change: '+12%', up: true },
                        { label: 'Revenue Today', value: '$4,820', change: '+23%', up: true },
                        { label: 'Avg Response', value: '2.4s', change: '-18%', up: true },
                        { label: 'CSAT Score', value: '4.9/5', change: '+5%', up: true },
                      ].map((stat) => (
                        <div key={stat.label} className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl p-3">
                          <p className="text-[10px] font-medium text-neutral-400 uppercase tracking-wider">{stat.label}</p>
                          <div className="flex items-baseline gap-1.5 mt-1">
                            <span className="text-lg font-bold text-neutral-900 dark:text-white">{stat.value}</span>
                            <span className="text-[10px] font-semibold text-green-500">{stat.change}</span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Mock conversation */}
                    <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-xl p-3.5 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-neutral-700 dark:text-neutral-200">Live Conversation</span>
                        <span className="text-[10px] font-medium text-green-500 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                          WhatsApp
                        </span>
                      </div>
                      <div className="space-y-2">
                        <div className="flex gap-2">
                          <div className="w-6 h-6 rounded-full bg-neutral-300 dark:bg-neutral-600 flex-shrink-0" />
                          <div className="bg-white dark:bg-neutral-700 rounded-lg rounded-tl-sm px-3 py-2 text-xs text-neutral-700 dark:text-neutral-200 max-w-[80%]">
                            Hi, do you have the wireless earbuds in black?
                          </div>
                        </div>
                        <div className="flex gap-2 justify-end">
                          <div className="bg-primary-600 rounded-lg rounded-tr-sm px-3 py-2 text-xs text-white max-w-[80%]">
                            Yes! The ProBuds X3 in matte black is in stock. It features 40hr battery, ANC, and comes with a 1-year warranty. Would you like me to send you the link?
                          </div>
                          <div className="w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center flex-shrink-0">
                            <Sparkles size={12} className="text-primary-600" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          METRICS STRIP
          ════════════════════════════════════════════════════════════════════ */}
      <section className="py-12 border-y border-neutral-100 dark:border-neutral-800/50 bg-neutral-50/50 dark:bg-neutral-900/30">
        <div className="section-container">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12">
            {METRICS.map((m, i) => (
              <motion.div
                key={m.label}
                className="text-center md:text-left"
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
              >
                <p className="text-3xl md:text-4xl font-bold text-neutral-900 dark:text-white">{m.value}</p>
                <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mt-1">{m.label}</p>
                <p className="text-xs text-neutral-400 dark:text-neutral-500">{m.sub}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          FEATURES — 3x2 grid, left-aligned cards
          ════════════════════════════════════════════════════════════════════ */}
      <section id="features" className="py-24 md:py-32">
        <div className="section-container">
          <motion.div
            className="max-w-2xl mb-16"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
              Features
            </motion.span>
            <motion.h2 variants={fadeUp} className="mt-3 text-balance">
              Everything you need to sell smarter
            </motion.h2>
            <motion.p variants={fadeUp} className="mt-4 text-lg text-neutral-500 dark:text-neutral-400 text-pretty">
              One platform to manage every customer conversation, automate responses, and close deals faster.
            </motion.p>
          </motion.div>

          <motion.div
            className="grid md:grid-cols-2 lg:grid-cols-3 gap-6"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            {FEATURES.map((f, i) => {
              const Icon = f.icon
              return (
                <motion.div
                  key={f.title}
                  variants={fadeUp}
                  custom={i}
                  className="group relative bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200/80 dark:border-neutral-800 p-7 card-lift cursor-default"
                >
                  <div className="flex items-start justify-between mb-5">
                    <div className="w-11 h-11 rounded-xl bg-primary-50 dark:bg-primary-950/40 flex items-center justify-center">
                      <Icon size={20} className="text-primary-600 dark:text-primary-400" />
                    </div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-400 bg-neutral-100 dark:bg-neutral-800 px-2.5 py-1 rounded-md">
                      {f.tag}
                    </span>
                  </div>
                  <h3 className="mb-2">{f.title}</h3>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400 leading-relaxed">{f.desc}</p>
                </motion.div>
              )
            })}
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          HOW IT WORKS — 3-step horizontal
          ════════════════════════════════════════════════════════════════════ */}
      <section className="py-24 md:py-32 bg-neutral-50 dark:bg-neutral-900/40 border-y border-neutral-100 dark:border-neutral-800/50">
        <div className="section-container">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-16"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
              How It Works
            </motion.span>
            <motion.h2 variants={fadeUp} className="mt-3">
              Live in 5 minutes
            </motion.h2>
          </motion.div>

          <motion.div
            className="grid md:grid-cols-3 gap-8 md:gap-12"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            {[
              { num: '01', title: 'Connect Channels', desc: 'Link WhatsApp, Email, Voice, Instagram, Facebook, or Web Chat. Takes 2 clicks per channel.' },
              { num: '02', title: 'Train Your AI', desc: 'Upload your knowledge base — PDFs, website URLs, product catalogs. Partython.ai learns your business in seconds.' },
              { num: '03', title: 'Go Live', desc: 'Partython.ai starts handling conversations instantly. Monitor, tweak, and handoff when needed.' },
            ].map((step, i) => (
              <motion.div key={step.num} variants={fadeUp} custom={i} className="relative">
                <span className="text-6xl md:text-7xl font-bold text-neutral-100 dark:text-neutral-800 leading-none">{step.num}</span>
                <h3 className="mt-3">{step.title}</h3>
                <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400 leading-relaxed">{step.desc}</p>
                {i < 2 && (
                  <div className="hidden md:block absolute top-8 -right-6 text-neutral-200 dark:text-neutral-700">
                    <ChevronRight size={24} />
                  </div>
                )}
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          INTEGRATIONS
          ════════════════════════════════════════════════════════════════════ */}
      <section className="py-24 md:py-32">
        <div className="section-container">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-16"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
              Integrations
            </motion.span>
            <motion.h2 variants={fadeUp} className="mt-3">
              Works with your stack
            </motion.h2>
            <motion.p variants={fadeUp} className="mt-4 text-neutral-500 dark:text-neutral-400">
              Connect to the tools you already use. No custom development needed.
            </motion.p>
          </motion.div>

          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-4"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            {INTEGRATIONS.map((intg, i) => (
              <motion.div
                key={intg.name}
                variants={fadeUp}
                custom={i}
                className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200/80 dark:border-neutral-800 p-5 text-center hover:shadow-md smooth"
              >
                <div className="w-12 h-12 mx-auto rounded-xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center mb-3">
                  <span className="text-lg font-bold text-neutral-700 dark:text-neutral-300">{intg.name[0]}</span>
                </div>
                <p className="text-sm font-semibold text-neutral-900 dark:text-white">{intg.name}</p>
                <p className="text-xs text-neutral-400 mt-1">{intg.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          CASE STUDIES
          ════════════════════════════════════════════════════════════════════ */}
      <section id="testimonials" className="py-24 md:py-32 bg-neutral-50 dark:bg-neutral-900/40 border-y border-neutral-100 dark:border-neutral-800/50">
        <div className="section-container">
          <motion.div
            className="max-w-2xl mb-16"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
              Case Studies
            </motion.span>
            <motion.h2 variants={fadeUp} className="mt-3 text-balance">
              Real results from real businesses
            </motion.h2>
          </motion.div>

          <motion.div
            className="grid md:grid-cols-3 gap-6"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            {CASE_STUDIES.map((cs, i) => (
              <motion.div
                key={cs.industry}
                variants={fadeUp}
                custom={i}
                className="relative bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200/80 dark:border-neutral-800 p-7 flex flex-col"
              >
                <div className="flex items-center justify-between mb-5">
                  <span className="text-xs font-semibold uppercase tracking-wider text-primary-600 bg-primary-50 dark:bg-primary-950/40 px-3 py-1.5 rounded-lg">
                    {cs.industry}
                  </span>
                  <div className="inline-flex items-center gap-1.5 text-xs font-bold text-green-600">
                    <Zap size={12} />
                    {cs.metric}
                  </div>
                </div>

                <div className="space-y-3 flex-1">
                  <div>
                    <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-1">Challenge</p>
                    <p className="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">{cs.challenge}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-1">Result</p>
                    <p className="text-sm text-neutral-700 dark:text-neutral-300 leading-relaxed">{cs.result}</p>
                  </div>
                </div>

                <div className="mt-5 pt-4 border-t border-neutral-100 dark:border-neutral-800 flex items-center gap-2">
                  <span className="text-xs text-neutral-400">Channels:</span>
                  {cs.channels.map(ch => (
                    <span key={ch} className="text-[10px] font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 px-2 py-0.5 rounded-md">{ch}</span>
                  ))}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          ABOUT / COMPANY
          ════════════════════════════════════════════════════════════════════ */}
      <section id="about" className="py-24 md:py-32">
        <div className="section-container">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <motion.div
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              variants={stagger}
            >
              <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
                About Partython
              </motion.span>
              <motion.h2 variants={fadeUp} className="mt-3 text-balance">
                Built by operators, for operators
              </motion.h2>
              <motion.p variants={fadeUp} className="mt-4 text-neutral-500 dark:text-neutral-400 leading-relaxed">
                Partython Inc was founded with a simple observation: e-commerce businesses spend 70% of their team bandwidth answering repetitive customer queries instead of growing revenue.
              </motion.p>
              <motion.p variants={fadeUp} className="mt-3 text-neutral-500 dark:text-neutral-400 leading-relaxed">
                We built Partython.ai to handle the conversations so teams can focus on what matters — building great products and delighting customers. Our platform processes over 44,000 orders and manages conversations across 6 channels for businesses in India and beyond.
              </motion.p>
              <motion.div variants={fadeUp} className="mt-8 grid grid-cols-3 gap-6">
                {[
                  { value: '2024', label: 'Founded' },
                  { value: 'Chennai', label: 'Headquarters' },
                  { value: '44K+', label: 'Orders Processed' },
                ].map(stat => (
                  <div key={stat.label}>
                    <p className="text-2xl font-bold text-neutral-900 dark:text-white">{stat.value}</p>
                    <p className="text-xs text-neutral-400 mt-0.5">{stat.label}</p>
                  </div>
                ))}
              </motion.div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="grid grid-cols-2 gap-4"
            >
              {[
                { icon: Shield, title: 'Security First', desc: 'End-to-end encryption, HMAC webhook verification, role-based access controls' },
                { icon: Globe, title: 'Multi-Language', desc: 'Supports English, Hindi, Tamil, Telugu and 20+ Indian languages' },
                { icon: Zap, title: 'Real-time Sync', desc: 'Shopify orders, customer data, and conversations sync instantly' },
                { icon: BarChart3, title: 'Analytics', desc: 'Revenue attribution, channel performance, and AI accuracy metrics' },
              ].map(item => {
                const Icon = item.icon
                return (
                  <div key={item.title} className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200/80 dark:border-neutral-800 p-5">
                    <Icon size={20} className="text-primary-600 mb-3" />
                    <p className="text-sm font-semibold text-neutral-900 dark:text-white">{item.title}</p>
                    <p className="text-xs text-neutral-400 mt-1 leading-relaxed">{item.desc}</p>
                  </div>
                )
              })}
            </motion.div>
          </div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          PRICING
          ════════════════════════════════════════════════════════════════════ */}
      <section id="pricing" className="py-24 md:py-32">
        <div className="section-container">
          <motion.div
            className="text-center max-w-2xl mx-auto mb-16"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.span variants={fadeUp} className="text-xs font-semibold text-primary-600 uppercase tracking-widest">
              Pricing
            </motion.span>
            <motion.h2 variants={fadeUp} className="mt-3">
              Simple, transparent pricing
            </motion.h2>
            <motion.p variants={fadeUp} className="mt-4 text-neutral-500 dark:text-neutral-400">
              Start free. Upgrade when you need more.
            </motion.p>
          </motion.div>

          <motion.div
            className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            {PLANS.map((plan, i) => (
              <motion.div
                key={plan.name}
                variants={fadeUp}
                custom={i}
                className={`relative bg-white dark:bg-neutral-900 rounded-2xl border p-7 flex flex-col ${
                  plan.highlight
                    ? 'border-primary-500 dark:border-primary-600 shadow-xl shadow-primary-600/10 ring-1 ring-primary-500/20'
                    : 'border-neutral-200/80 dark:border-neutral-800'
                }`}
              >
                {plan.badge && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary-600 text-white text-[10px] font-bold uppercase tracking-wider px-4 py-1 rounded-full">
                    {plan.badge}
                  </span>
                )}

                <div className="mb-6">
                  <h3 className="text-lg font-semibold">{plan.name}</h3>
                  <p className="text-xs text-neutral-400 mt-1">{plan.desc}</p>
                </div>

                <div className="mb-6">
                  <span className="text-4xl font-bold text-neutral-900 dark:text-white">{plan.price}</span>
                  <span className="text-sm text-neutral-400">{plan.period}</span>
                </div>

                <Link
                  href="/register"
                  className={`w-full inline-flex items-center justify-center gap-2 font-semibold text-sm py-3 rounded-xl no-underline smooth mb-6 ${
                    plan.highlight
                      ? 'bg-primary-600 hover:bg-primary-700 text-white shadow-sm shadow-primary-600/25'
                      : 'border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                  }`}
                >
                  {plan.cta}
                  <ArrowRight size={14} />
                </Link>

                <div className="space-y-3 flex-1">
                  {plan.features.map((f) => (
                    <div key={f} className="flex items-start gap-2.5">
                      <CheckCircle size={15} className="text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-sm text-neutral-600 dark:text-neutral-400">{f}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          FINAL CTA
          ════════════════════════════════════════════════════════════════════ */}
      <section className="py-24 md:py-32 relative overflow-hidden">
        <div className="absolute inset-0 bg-neutral-900 dark:bg-neutral-950" />
        <div className="absolute inset-0 dot-grid opacity-30" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-primary-600/15 rounded-full blur-3xl pointer-events-none" />

        <div className="section-container relative text-center">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={stagger}
          >
            <motion.h2 variants={fadeUp} className="text-white text-balance">
              Ready to let AI handle your sales?
            </motion.h2>
            <motion.p variants={fadeUp} className="mt-4 text-lg text-neutral-400 max-w-xl mx-auto">
              Join 1,000+ companies using Partython.ai to respond faster, sell more, and delight every customer.
            </motion.p>
            <motion.div variants={fadeUp} className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                href="/register"
                className="inline-flex items-center justify-center gap-2 bg-white hover:bg-neutral-100 text-neutral-900 font-semibold text-sm px-7 py-3.5 rounded-xl no-underline smooth"
              >
                Start Free Trial
                <ArrowRight size={16} />
              </Link>
              <Link
                href="#pricing"
                className="inline-flex items-center justify-center gap-2 text-neutral-300 font-medium text-sm px-6 py-3.5 rounded-xl border border-neutral-700 hover:border-neutral-500 hover:text-white no-underline smooth"
              >
                View Pricing
              </Link>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ════════════════════════════════════════════════════════════════════
          FOOTER
          ════════════════════════════════════════════════════════════════════ */}
      <footer className="bg-neutral-900 dark:bg-neutral-950 border-t border-neutral-800 py-16">
        <div className="section-container">
          <div className="grid md:grid-cols-5 gap-10 mb-12">
            {/* Brand */}
            <div className="md:col-span-2">
              <div className="flex items-center gap-2.5 mb-4">
                <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold text-sm">P</div>
                <span className="text-base font-bold text-white tracking-tight">Partython.ai</span>
              </div>
              <p className="text-sm text-neutral-400 leading-relaxed max-w-xs">
                Your AI Sales Team, Always On. Built for businesses that take customer experience seriously.
              </p>

              {/* Channel icons in footer */}
              <div className="flex items-center gap-2 mt-5">
                {CHANNELS.map((ch) => (
                  <div key={ch.name} title={ch.name}>
                    <ChannelIcon channel={ch} size={28} />
                  </div>
                ))}
              </div>
            </div>

            {/* Links */}
            <div>
              <h4 className="text-sm font-semibold text-white mb-4">Product</h4>
              <ul className="space-y-2.5">
                <li><a href="#features" className="text-sm text-neutral-400 hover:text-white no-underline smooth">Features</a></li>
                <li><a href="#pricing" className="text-sm text-neutral-400 hover:text-white no-underline smooth">Pricing</a></li>
                <li><a href="#testimonials" className="text-sm text-neutral-400 hover:text-white no-underline smooth">Case Studies</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-white mb-4">Company</h4>
              <ul className="space-y-2.5">
                <li><a href="#about" className="text-sm text-neutral-400 hover:text-white no-underline smooth">About</a></li>
                <li><a href="mailto:support@partython.com" className="text-sm text-neutral-400 hover:text-white no-underline smooth">Contact</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-white mb-4">Contact</h4>
              <ul className="space-y-2.5">
                <li className="text-sm text-neutral-400">support@partython.com</li>
                <li className="text-sm text-neutral-400">Chennai, India</li>
              </ul>
            </div>
          </div>

          <div className="border-t border-neutral-800 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-xs text-neutral-500">&copy; 2026 Partython.ai Technologies. All rights reserved.</p>
            <div className="flex items-center gap-6">
              <a href="#" className="text-xs text-neutral-500 hover:text-neutral-300 no-underline">Privacy</a>
              <a href="#" className="text-xs text-neutral-500 hover:text-neutral-300 no-underline">Terms</a>
              <a href="#" className="text-xs text-neutral-500 hover:text-neutral-300 no-underline">Cookies</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
