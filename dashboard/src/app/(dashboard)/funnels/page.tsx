// @ts-nocheck
'use client'

import React from 'react'
import { TrendingUp, ArrowRight, Users, MessageSquare, ShoppingCart, CreditCard } from 'lucide-react'

const funnelStages = [
  { name: 'Visitors', value: 12500, icon: Users, color: 'bg-blue-500', pct: 100 },
  { name: 'Engaged', value: 4200, icon: MessageSquare, color: 'bg-indigo-500', pct: 33.6 },
  { name: 'Interested', value: 1850, icon: TrendingUp, color: 'bg-purple-500', pct: 14.8 },
  { name: 'Cart Added', value: 920, icon: ShoppingCart, color: 'bg-pink-500', pct: 7.4 },
  { name: 'Purchased', value: 380, icon: CreditCard, color: 'bg-green-500', pct: 3.0 },
]

const channelFunnels = [
  { channel: 'WhatsApp', visitors: 5200, engaged: 2100, interested: 980, cart: 490, purchased: 210, convRate: '4.0%' },
  { channel: 'Email', visitors: 3800, engaged: 950, interested: 420, cart: 210, purchased: 85, convRate: '2.2%' },
  { channel: 'Instagram', visitors: 2100, engaged: 780, interested: 310, cart: 150, purchased: 58, convRate: '2.8%' },
  { channel: 'Voice', visitors: 800, engaged: 280, interested: 110, cart: 55, purchased: 22, convRate: '2.8%' },
  { channel: 'WebChat', visitors: 600, engaged: 90, interested: 30, cart: 15, purchased: 5, convRate: '0.8%' },
]

export default function FunnelsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Sales Funnels</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">Track conversion rates from first contact to purchase</p>
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-50 mb-6">Overall Funnel</h2>
        <div className="flex items-center justify-between gap-2">
          {funnelStages.map((stage, i) => (
            <React.Fragment key={stage.name}>
              <div className="flex-1 text-center">
                <div className={`${stage.color} mx-auto w-14 h-14 rounded-xl flex items-center justify-center text-white mb-3`}>
                  <stage.icon size={24} />
                </div>
                <p className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">{stage.value.toLocaleString()}</p>
                <p className="text-sm text-neutral-500 mt-0.5">{stage.name}</p>
                <p className="text-xs text-neutral-400 mt-0.5">{stage.pct}%</p>
              </div>
              {i < funnelStages.length - 1 && (
                <ArrowRight size={20} className="text-neutral-300 dark:text-neutral-600 flex-shrink-0" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="p-6 border-b border-neutral-200 dark:border-neutral-800">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-50">By Channel</h2>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-800/50">
              {['Channel', 'Visitors', 'Engaged', 'Interested', 'Cart', 'Purchased', 'Conv. Rate'].map((h) => (
                <th key={h} className="text-left px-6 py-3 text-xs font-semibold text-neutral-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
            {channelFunnels.map((cf) => (
              <tr key={cf.channel} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition">
                <td className="px-6 py-4 font-medium text-neutral-900 dark:text-neutral-50">{cf.channel}</td>
                <td className="px-6 py-4 text-sm text-neutral-600 dark:text-neutral-400">{cf.visitors.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm text-neutral-600 dark:text-neutral-400">{cf.engaged.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm text-neutral-600 dark:text-neutral-400">{cf.interested.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm text-neutral-600 dark:text-neutral-400">{cf.cart.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm font-medium text-green-600">{cf.purchased.toLocaleString()}</td>
                <td className="px-6 py-4 text-sm font-semibold text-primary-600 dark:text-primary-400">{cf.convRate}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
