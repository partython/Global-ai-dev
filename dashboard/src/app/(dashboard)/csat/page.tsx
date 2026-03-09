// @ts-nocheck
'use client'

import React from 'react'
import { Star, TrendingUp, MessageSquare, ThumbsUp, ThumbsDown } from 'lucide-react'

const csatData = [
  { period: 'This Week', score: 4.6, responses: 145, positive: 89, neutral: 8, negative: 3 },
  { period: 'Last Week', score: 4.4, responses: 132, positive: 85, neutral: 10, negative: 5 },
  { period: 'This Month', score: 4.5, responses: 580, positive: 87, neutral: 9, negative: 4 },
]

const recentFeedback = [
  { id: '1', customer: 'Priya S.', rating: 5, comment: 'Amazing service! Priya AI was incredibly helpful in choosing the right party supplies.', channel: 'WhatsApp', time: '2h ago' },
  { id: '2', customer: 'Rahul P.', rating: 4, comment: 'Quick response, good recommendations. Would appreciate more payment options.', channel: 'Email', time: '4h ago' },
  { id: '3', customer: 'Anita D.', rating: 5, comment: 'Best customer service I\'ve experienced online. The voice call was seamless.', channel: 'Voice', time: '6h ago' },
  { id: '4', customer: 'Vikram S.', rating: 3, comment: 'Decent but took a while to understand my requirements. Could improve on complex queries.', channel: 'Instagram', time: '1d ago' },
  { id: '5', customer: 'Meera N.', rating: 5, comment: 'Love the AI agent! It remembered my preferences from last time.', channel: 'WebChat', time: '1d ago' },
]

export default function CSATPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">Customer Satisfaction</h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-1">Track CSAT scores and customer feedback across all channels</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: 'Overall CSAT', value: '4.5/5', icon: Star, color: 'text-yellow-500', bg: 'bg-yellow-50 dark:bg-yellow-900/20' },
          { label: 'Total Responses', value: '580', icon: MessageSquare, color: 'text-primary-500', bg: 'bg-primary-50 dark:bg-primary-900/20' },
          { label: 'Positive Rate', value: '87%', icon: ThumbsUp, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-900/20' },
          { label: 'Improvement', value: '+2.3%', icon: TrendingUp, color: 'text-accent-500', bg: 'bg-accent-50 dark:bg-accent-900/20' },
        ].map((stat) => (
          <div key={stat.label} className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-neutral-500 dark:text-neutral-400">{stat.label}</span>
              <div className={`p-2 rounded-lg ${stat.bg}`}><stat.icon size={18} className={stat.color} /></div>
            </div>
            <p className="text-2xl font-bold text-neutral-900 dark:text-neutral-50">{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-50 mb-4">Period Breakdown</h2>
        <div className="space-y-4">
          {csatData.map((d) => (
            <div key={d.period} className="flex items-center justify-between p-4 bg-neutral-50 dark:bg-neutral-800/50 rounded-lg">
              <div>
                <p className="font-medium text-neutral-900 dark:text-neutral-50">{d.period}</p>
                <p className="text-sm text-neutral-500">{d.responses} responses</p>
              </div>
              <div className="flex items-center gap-6 text-sm">
                <span className="text-green-600">{d.positive}% positive</span>
                <span className="text-neutral-400">{d.neutral}% neutral</span>
                <span className="text-red-500">{d.negative}% negative</span>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star key={s} size={16} className={s <= Math.round(d.score) ? 'text-yellow-400 fill-yellow-400' : 'text-neutral-300'} />
                  ))}
                  <span className="ml-1 font-semibold text-neutral-900 dark:text-neutral-50">{d.score}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-neutral-900 rounded-xl border border-neutral-200 dark:border-neutral-800 p-6">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-50 mb-4">Recent Feedback</h2>
        <div className="space-y-3">
          {recentFeedback.map((fb) => (
            <div key={fb.id} className="p-4 border border-neutral-100 dark:border-neutral-800 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-neutral-900 dark:text-neutral-50">{fb.customer}</span>
                  <span className="text-xs px-2 py-0.5 bg-neutral-100 dark:bg-neutral-800 rounded-full text-neutral-500">{fb.channel}</span>
                </div>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star key={s} size={14} className={s <= fb.rating ? 'text-yellow-400 fill-yellow-400' : 'text-neutral-300'} />
                  ))}
                  <span className="ml-2 text-xs text-neutral-400">{fb.time}</span>
                </div>
              </div>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">{fb.comment}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
