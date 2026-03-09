'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Wallet,
  ArrowUpCircle,
  ArrowDownCircle,
  RefreshCw,
  IndianRupee,
  Clock,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useAuthStore } from '@/stores/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000'

interface Transaction {
  id: string
  type: 'topup' | 'debit' | 'refund' | 'adjustment'
  amount_paisa: number
  amount_display: string
  running_balance_paisa: number
  channel: string | null
  reference_id: string | null
  description: string | null
  created_at: string | null
}

interface WalletBalance {
  wallet_id: string
  balance_paisa: number
  balance_display: string
  currency: string
  auto_topup: {
    enabled: boolean
    threshold_paisa: number
    topup_amount_paisa: number
  }
}

export default function WalletPage() {
  const token = useAuthStore((s) => s.token)
  const [balance, setBalance] = useState<WalletBalance | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [topupAmount, setTopupAmount] = useState('')
  const [topupLoading, setTopupLoading] = useState(false)

  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const fetchBalance = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/wallet/balance`, { headers })
      if (res.ok) setBalance(await res.json())
    } catch (e) {
      console.error('Failed to fetch balance', e)
    }
  }, [token])

  const fetchTransactions = useCallback(async (p: number) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/wallet/transactions?page=${p}&per_page=15`, { headers })
      if (res.ok) {
        const data = await res.json()
        setTransactions(data.transactions)
        setTotalPages(data.pagination.pages)
      }
    } catch (e) {
      console.error('Failed to fetch transactions', e)
    }
  }, [token])

  useEffect(() => {
    Promise.all([fetchBalance(), fetchTransactions(1)]).finally(() => setLoading(false))
  }, [fetchBalance, fetchTransactions])

  const handleTopup = async () => {
    const amountRupees = parseFloat(topupAmount)
    if (!amountRupees || amountRupees < 100) return alert('Minimum topup is ₹100')
    if (amountRupees > 100000) return alert('Maximum topup is ₹1,00,000')

    setTopupLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/wallet/topup-order`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          amount_paisa: Math.round(amountRupees * 100),
          currency: 'INR',
        }),
      })
      const order = await res.json()
      if (!res.ok) throw new Error(order.detail || 'Failed to create order')

      // Open Razorpay checkout
      const options = {
        key: order.razorpay_key_id,
        amount: order.amount_paisa,
        currency: order.currency,
        name: 'Partython.ai',
        description: 'Wallet Topup',
        order_id: order.razorpay_order_id,
        handler: async (response: any) => {
          // Verify payment
          const verifyRes = await fetch(`${API_URL}/api/v1/wallet/topup-verify`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            }),
          })
          const result = await verifyRes.json()
          if (verifyRes.ok) {
            setTopupAmount('')
            await fetchBalance()
            await fetchTransactions(1)
          } else {
            alert(result.detail || 'Payment verification failed')
          }
        },
        prefill: {},
        theme: { color: '#7c3aed' },
      }

      // @ts-ignore - Razorpay loaded via script
      const rzp = new window.Razorpay(options)
      rzp.open()
    } catch (e: any) {
      alert(e.message || 'Topup failed')
    } finally {
      setTopupLoading(false)
    }
  }

  const typeColors: Record<string, string> = {
    topup: 'text-green-600 bg-green-50 dark:bg-green-900/20',
    debit: 'text-red-600 bg-red-50 dark:bg-red-900/20',
    refund: 'text-blue-600 bg-blue-50 dark:bg-blue-900/20',
    adjustment: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20',
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="w-8 h-8 border-3 border-primary-600/30 border-t-primary-600 rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
          <Wallet className="text-primary-600" size={24} />
          Wallet
        </h1>
        <p className="text-sm text-neutral-500 mt-1">Prepaid credits for messages, calls, and AI usage</p>
      </div>

      {/* Balance Card + Topup */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Balance */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-gradient-to-br from-primary-600 to-primary-800 rounded-2xl p-6 text-white shadow-lg shadow-primary-600/20"
        >
          <p className="text-sm font-medium text-primary-200">Current Balance</p>
          <p className="text-4xl font-bold mt-2 flex items-baseline gap-1">
            <IndianRupee size={28} strokeWidth={2.5} />
            {balance ? (balance.balance_paisa / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '0.00'}
          </p>
          <p className="text-xs text-primary-300 mt-3">
            {balance?.auto_topup?.enabled
              ? `Auto-topup enabled below ₹${(balance.auto_topup.threshold_paisa / 100).toFixed(0)}`
              : 'Auto-topup disabled'}
          </p>
        </motion.div>

        {/* Topup */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white dark:bg-neutral-900 rounded-2xl p-6 border border-neutral-200 dark:border-neutral-800"
        >
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">Add Credits</p>
          <div className="mt-3 flex gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400 text-sm">₹</span>
              <input
                type="number"
                value={topupAmount}
                onChange={(e) => setTopupAmount(e.target.value)}
                className="w-full pl-7 pr-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-white outline-none text-sm"
                placeholder="500"
                min={100}
                max={100000}
              />
            </div>
            <button
              onClick={handleTopup}
              disabled={topupLoading}
              className="px-5 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth disabled:opacity-50"
            >
              {topupLoading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                'Top Up'
              )}
            </button>
          </div>
          {/* Quick amounts */}
          <div className="flex gap-2 mt-3">
            {[500, 1000, 2500, 5000].map((amt) => (
              <button
                key={amt}
                onClick={() => setTopupAmount(String(amt))}
                className="px-3 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 text-xs font-medium text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800 smooth"
              >
                ₹{amt.toLocaleString('en-IN')}
              </button>
            ))}
          </div>
        </motion.div>
      </div>

      {/* Transaction History */}
      <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 overflow-hidden">
        <div className="px-6 py-4 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
          <h2 className="font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
            <Clock size={16} />
            Transaction History
          </h2>
          <button
            onClick={() => { fetchBalance(); fetchTransactions(page) }}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        {transactions.length === 0 ? (
          <div className="px-6 py-12 text-center text-neutral-400 text-sm">
            No transactions yet. Top up your wallet to get started.
          </div>
        ) : (
          <>
            <div className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {transactions.map((tx) => (
                <div key={tx.id} className="px-6 py-3.5 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${typeColors[tx.type] || ''}`}>
                      {tx.type === 'topup' ? <ArrowUpCircle size={16} /> : <ArrowDownCircle size={16} />}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-neutral-900 dark:text-white capitalize">{tx.type}</p>
                      <p className="text-xs text-neutral-400">{tx.description || tx.channel || '—'}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-sm font-semibold ${tx.type === 'topup' || tx.type === 'refund' ? 'text-green-600' : 'text-red-600'}`}>
                      {tx.type === 'topup' || tx.type === 'refund' ? '+' : '-'}{tx.amount_display}
                    </p>
                    <p className="text-xs text-neutral-400">
                      {tx.created_at ? new Date(tx.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="px-6 py-3 border-t border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
                <button
                  onClick={() => { const p = Math.max(1, page - 1); setPage(p); fetchTransactions(p) }}
                  disabled={page <= 1}
                  className="text-sm text-neutral-500 flex items-center gap-1 disabled:opacity-30"
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <span className="text-xs text-neutral-400">Page {page} of {totalPages}</span>
                <button
                  onClick={() => { const p = Math.min(totalPages, page + 1); setPage(p); fetchTransactions(p) }}
                  disabled={page >= totalPages}
                  className="text-sm text-neutral-500 flex items-center gap-1 disabled:opacity-30"
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
