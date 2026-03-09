// @ts-nocheck
'use client'

import React from 'react'
import { UserPlus, Clock, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react'

const handoffs = [
  { id: '1', customer: 'Priya Sharma', reason: 'Complex pricing query for bulk order', channel: 'WhatsApp', status: 'pending', priority: 'high', assignedTo: null, time: '5 min ago', aiContext: 'Customer wants 500+ balloon sets with custom printing. AI could not confirm bulk pricing.' },
  { id: '2', customer: 'Vikram Singh', reason: 'Complaint about late delivery', channel: 'Email', status: 'in_progress', priority: 'urgent', assignedTo: 'Uma', time: '12 min ago', aiContext: 'Order #4521 was promised for yesterday. Customer is frustrated.' },
  { id: '3', customer: 'Rahul Patel', reason: 'Refund request for damaged items', channel: 'Voice', status: 'in_progress', priority: 'high', assignedTo: 'Uma', time: '25 min ago', aiContext: 'Customer received torn decorations. Wants full refund + replacement.' },
  { id: '4', customer: 'Meera Nair', reason: 'Corporate event planning consultation', channel: 'Instagram', status: 'resolved', priority: 'normal', assignedTo: 'Uma', time: '2 hours ago', aiContext: 'Large corporate party for 200 guests. Needs custom theme consultation.' },
  { id: '5', customer: 'Anita Desai', reason: 'Payment gateway issue', channel: 'WebChat', status: 'resolved', priority: 'high', assignedTo: 'Uma', time: '3 hours ago', aiContext: 'Payment failed twice but amount deducted. Needs manual verification.' },
]

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  resolved: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
}

const priorityColors: Record<string, string> = {
  urgent: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  normal: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400',
}

export default function HandoffsPage() {
  const pending = handoffs.filter((h) => h.status === 'pending').length
  const inProgress = handoffs.filter((h) => h.status === 'in_progress').length
  const resolved = handoffs.filter((h) => h.status === 'resolved').length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Agent Handoffs</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">Conversations escalated from AI to human agents</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: 'Pending', value: pending, icon: AlertCircle, color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20' },
          { label: 'In Progress', value: inProgress, icon: Clock, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20' },
          { label: 'Resolved Today', value: resolved, icon: CheckCircle, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
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

      <div className="space-y-3">
        {handoffs.map((h) => (
          <div key={h.id} className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-5">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold text-sm">
                  {h.customer.split(' ').map((n) => n[0]).join('')}
                </div>
                <div>
                  <p className="font-medium text-neutral-900 dark:text-neutral-50">{h.customer}</p>
                  <p className="text-sm text-neutral-500">{h.reason}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${priorityColors[h.priority]}`}>{h.priority}</span>
                <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${statusColors[h.status]}`}>{h.status.replace('_', ' ')}</span>
              </div>
            </div>
            <div className="bg-neutral-50 dark:bg-neutral-800/50 rounded-lg p-3 text-sm text-neutral-600 dark:text-neutral-400">
              <span className="font-medium text-neutral-700 dark:text-neutral-300">AI Context:</span> {h.aiContext}
            </div>
            <div className="flex items-center justify-between mt-3 text-xs text-neutral-400">
              <span>{h.channel} &middot; {h.time}</span>
              {h.assignedTo && <span>Assigned to: <span className="font-medium text-neutral-600 dark:text-neutral-300">{h.assignedTo}</span></span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
