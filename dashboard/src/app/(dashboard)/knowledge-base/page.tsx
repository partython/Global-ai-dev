// @ts-nocheck
'use client'

import React, { useState } from 'react'
import { BookOpen, Upload, Search, FileText, Globe, MessageSquare, Clock, CheckCircle, Plus } from 'lucide-react'

const sources = [
  { id: '1', name: 'Product Catalog 2026', type: 'document', status: 'indexed', items: 342, lastUpdated: '2 hours ago', icon: FileText },
  { id: '2', name: 'partysuppliesindia.com', type: 'website', status: 'indexed', items: 156, lastUpdated: '1 day ago', icon: Globe },
  { id: '3', name: 'FAQ Database', type: 'document', status: 'indexed', items: 89, lastUpdated: '3 days ago', icon: MessageSquare },
  { id: '4', name: 'Pricing & Shipping Guide', type: 'document', status: 'indexing', items: 45, lastUpdated: 'Just now', icon: FileText },
  { id: '5', name: 'Customer Support Playbook', type: 'document', status: 'indexed', items: 67, lastUpdated: '1 week ago', icon: BookOpen },
]

export default function KnowledgeBasePage() {
  const [search, setSearch] = useState('')
  const totalItems = sources.reduce((sum, s) => sum + s.items, 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Knowledge Base</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">{totalItems} items indexed across {sources.length} sources</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-primary-600 to-accent-600 text-white font-semibold rounded-lg hover:opacity-90 transition">
          <Plus size={18} /> Add Source
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: 'Total Items', value: totalItems.toLocaleString(), icon: BookOpen, color: 'text-primary-500', bg: 'bg-primary-50 dark:bg-primary-900/20' },
          { label: 'Sources', value: sources.length, icon: FileText, color: 'text-accent-500', bg: 'bg-accent-50 dark:bg-accent-900/20' },
          { label: 'AI Accuracy', value: '94.2%', icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
        ].map((stat) => (
          <div key={stat.label} className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-5 flex items-center gap-4">
            <div className={`p-3 rounded-xl ${stat.bg}`}><stat.icon size={22} className={stat.color} /></div>
            <div>
              <p className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">{stat.value}</p>
              <p className="text-sm text-neutral-500">{stat.label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search knowledge base..."
          className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-primary-500 outline-none transition"
        />
      </div>

      <div className="space-y-3">
        {sources.map((s) => (
          <div key={s.id} className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-5 flex items-center justify-between hover:shadow-md transition cursor-pointer">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-neutral-100 dark:bg-neutral-800">
                <s.icon size={22} className="text-neutral-600 dark:text-neutral-400" />
              </div>
              <div>
                <p className="font-medium text-neutral-900 dark:text-neutral-50">{s.name}</p>
                <p className="text-sm text-neutral-500">{s.items} items &middot; {s.type}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="flex items-center gap-1.5">
                  {s.status === 'indexed' ? (
                    <><CheckCircle size={14} className="text-green-500" /><span className="text-xs text-green-600 font-medium">Indexed</span></>
                  ) : (
                    <><Clock size={14} className="text-yellow-500 animate-spin" /><span className="text-xs text-yellow-600 font-medium">Indexing...</span></>
                  )}
                </div>
                <p className="text-xs text-neutral-400 mt-0.5">{s.lastUpdated}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
