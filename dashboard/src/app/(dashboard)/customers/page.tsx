// @ts-nocheck
'use client'

import React, { useState } from 'react'
import { Search, Filter, Download, ChevronDown, Mail, Phone, MessageSquare, Star } from 'lucide-react'

const mockCustomers = [
  { id: '1', name: 'Priya Sharma', email: 'priya@example.com', phone: '+91 98765 43210', channel: 'WhatsApp', leadScore: 92, totalSpent: 15400, conversations: 12, lastContact: '2 hours ago', status: 'active', tags: ['VIP', 'Repeat'] },
  { id: '2', name: 'Rahul Patel', email: 'rahul@example.com', phone: '+91 87654 32109', channel: 'Email', leadScore: 78, totalSpent: 8200, conversations: 5, lastContact: '1 day ago', status: 'active', tags: ['New Lead'] },
  { id: '3', name: 'Anita Desai', email: 'anita@example.com', phone: '+91 76543 21098', channel: 'Instagram', leadScore: 85, totalSpent: 22100, conversations: 18, lastContact: '3 hours ago', status: 'active', tags: ['VIP', 'Corporate'] },
  { id: '4', name: 'Vikram Singh', email: 'vikram@example.com', phone: '+91 65432 10987', channel: 'Voice', leadScore: 45, totalSpent: 3200, conversations: 3, lastContact: '5 days ago', status: 'inactive', tags: ['Cold Lead'] },
  { id: '5', name: 'Meera Nair', email: 'meera@example.com', phone: '+91 54321 09876', channel: 'WebChat', leadScore: 88, totalSpent: 18500, conversations: 15, lastContact: '30 min ago', status: 'active', tags: ['Repeat', 'High Value'] },
]

export default function CustomersPage() {
  const [search, setSearch] = useState('')
  const filtered = mockCustomers.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Customers</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">{mockCustomers.length} total customers across all channels</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm font-medium hover:bg-neutral-50 dark:hover:bg-neutral-700 transition">
          <Download size={16} /> Export
        </button>
      </div>

      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customers by name or email..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 focus:ring-2 focus:ring-primary-500 outline-none transition"
          />
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm font-medium hover:bg-neutral-50 dark:hover:bg-neutral-700 transition">
          <Filter size={16} /> Filter <ChevronDown size={14} />
        </button>
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50">
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Customer</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Channel</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Lead Score</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Total Spent</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Last Contact</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">Tags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {filtered.map((c) => (
              <tr key={c.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition cursor-pointer">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary-400 to-accent-400 flex items-center justify-center text-white font-semibold text-sm">
                      {c.name.split(' ').map((n) => n[0]).join('')}
                    </div>
                    <div>
                      <p className="font-medium text-neutral-900 dark:text-neutral-50">{c.name}</p>
                      <p className="text-xs text-neutral-500">{c.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-neutral-600 dark:text-neutral-400">{c.channel}</td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${c.leadScore >= 80 ? 'bg-green-500' : c.leadScore >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${c.leadScore}%` }} />
                    </div>
                    <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{c.leadScore}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm font-medium text-neutral-900 dark:text-neutral-50">${c.totalSpent.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm text-neutral-500 dark:text-neutral-400">{c.lastContact}</td>
                <td className="px-6 py-4">
                  <div className="flex gap-1 flex-wrap">
                    {c.tags.map((tag) => (
                      <span key={tag} className="px-2 py-0.5 bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 text-xs rounded-full font-medium">{tag}</span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
