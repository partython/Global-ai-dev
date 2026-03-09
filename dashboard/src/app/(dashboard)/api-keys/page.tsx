// @ts-nocheck
'use client';

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Copy,
  Eye,
  EyeOff,
  Trash2,
  RotateCcw,
  Plus,
  Code2,
  Zap,
  Shield,
  Clock,
  AlertCircle,
  Check,
  X,
  CheckCheck,
  Activity,
  Webhook,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

// Mock data
const mockApiKeys = [
  {
    id: '1',
    name: 'Production Key',
    key: 'pk_live_a1b2c3d4e5f6g7h8i9j0',
    createdDate: '2025-11-15',
    lastUsed: '2026-03-07 14:32:00',
    status: 'active',
    permissions: ['Read Conversations', 'Write Messages', 'Manage Contacts', 'Webhooks'],
  },
  {
    id: '2',
    name: 'Staging Key',
    key: 'pk_test_x9y8z7w6v5u4t3s2r1q0',
    createdDate: '2025-10-22',
    lastUsed: '2026-03-05 09:15:00',
    status: 'active',
    permissions: ['Read Conversations', 'Write Messages', 'Analytics'],
  },
  {
    id: '3',
    name: 'Analytics Read-Only',
    key: 'pk_live_m1n2o3p4q5r6s7t8u9v0',
    createdDate: '2025-09-10',
    lastUsed: '2026-03-01 16:45:00',
    status: 'active',
    permissions: ['Analytics'],
  },
  {
    id: '4',
    name: 'Webhook Testing',
    key: 'pk_test_h1g2f3e4d5c6b7a8z9y0',
    createdDate: '2025-08-30',
    lastUsed: '2026-02-28 11:22:00',
    status: 'revoked',
    permissions: ['Webhooks', 'Read Conversations'],
  },
];

const mockWebhooks = [
  {
    id: '1',
    url: 'https://api.example.com/webhooks/messages',
    events: ['message.received', 'message.sent'],
    status: 'active',
    lastDelivery: '2026-03-07 14:28:00',
    deliveryRate: 99.8,
  },
  {
    id: '2',
    url: 'https://analytics.example.com/webhooks/events',
    events: ['conversation.created', 'conversation.ended'],
    status: 'active',
    lastDelivery: '2026-03-07 14:15:00',
    deliveryRate: 99.5,
  },
  {
    id: '3',
    url: 'https://backup.example.com/webhooks/sync',
    events: ['contact.updated', 'settings.changed'],
    status: 'inactive',
    lastDelivery: '2026-03-04 08:30:00',
    deliveryRate: 95.2,
  },
];

const mockUsageData = [
  { date: '03-06', calls: 2400, latency: 45 },
  { date: '03-05', calls: 1398, latency: 52 },
  { date: '03-04', calls: 3200, latency: 48 },
  { date: '03-03', calls: 2780, latency: 56 },
  { date: '03-02', calls: 1890, latency: 41 },
  { date: '03-01', calls: 2390, latency: 49 },
  { date: '02-28', calls: 3490, latency: 54 },
];

const mockRateLimits = [
  {
    endpoint: 'Conversations',
    limit: '1000 req/min',
    current: 487,
    percentage: 48.7,
  },
  {
    endpoint: 'Messages',
    limit: '5000 req/min',
    current: 1234,
    percentage: 24.68,
  },
  {
    endpoint: 'Contacts',
    limit: '2000 req/min',
    current: 892,
    percentage: 44.6,
  },
  {
    endpoint: 'Analytics',
    limit: '500 req/min',
    current: 312,
    percentage: 62.4,
  },
];

const codeSnippets = {
  curl: `curl -X GET https://api.partython.in/v1/conversations \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json"`,
  python: `import requests

headers = {
    'Authorization': 'Bearer YOUR_API_KEY',
    'Content-Type': 'application/json'
}

response = requests.get(
    'https://api.partython.in/v1/conversations',
    headers=headers
)

print(response.json())`,
  nodejs: `const axios = require('axios');

const headers = {
  'Authorization': 'Bearer YOUR_API_KEY',
  'Content-Type': 'application/json'
};

axios.get('https://api.partython.in/v1/conversations', { headers })
  .then(response => console.log(response.data))
  .catch(error => console.error(error));`,
  php: `<?php
$curl = curl_init();

curl_setopt_array($curl, array(
  CURLOPT_URL => 'https://api.partython.in/v1/conversations',
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_HTTPHEADER => array(
    'Authorization: Bearer YOUR_API_KEY',
    'Content-Type: application/json'
  )
));

$response = curl_exec($curl);
echo json_encode(json_decode($response));
?>`,
};

interface ApiKey {
  id: string;
  name: string;
  key: string;
  createdDate: string;
  lastUsed: string;
  status: 'active' | 'revoked';
  permissions: string[];
}

interface Webhook {
  id: string;
  url: string;
  events: string[];
  status: 'active' | 'inactive';
  lastDelivery: string;
  deliveryRate: number;
}

export default function ApiKeysPage() {
  const [apiKeys, setApiKeys] = useState<ApiKey[]>(mockApiKeys as ApiKey[]);
  const [webhooks, setWebhooks] = useState<Webhook[]>(mockWebhooks as Webhook[]);
  const [isLoading, setIsLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [revealedKeys, setRevealedKeys] = useState<{ [key: string]: boolean }>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [activeCodeTab, setActiveCodeTab] = useState<'curl' | 'python' | 'nodejs' | 'php'>('curl');
  const [formData, setFormData] = useState({
    name: '',
    permissions: [] as string[],
    expiryDays: '',
  });
  const { user } = useAuthStore();

  useEffect(() => {
    // In a real app, fetch from API
    // fetchApiKeys();
  }, []);

  const maskApiKey = (key: string) => {
    const visible = key.slice(-4);
    return `pk_live_****${visible}`;
  };

  const handleCopyKey = (key: string, keyId: string) => {
    navigator.clipboard.writeText(key);
    setCopiedKey(keyId);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleRevealKey = (keyId: string) => {
    setRevealedKeys((prev) => ({
      ...prev,
      [keyId]: !prev[keyId],
    }));
  };

  const handlePermissionToggle = (permission: string) => {
    setFormData((prev) => ({
      ...prev,
      permissions: prev.permissions.includes(permission)
        ? prev.permissions.filter((p) => p !== permission)
        : [...prev.permissions, permission],
    }));
  };

  const handleCreateKey = async () => {
    if (!formData.name || formData.permissions.length === 0) {
      alert('Please fill in all required fields');
      return;
    }

    setIsLoading(true);
    try {
      // In a real app, call apiClient.post('/api/v1/settings/api-keys', formData);
      const newKey: ApiKey = {
        id: Date.now().toString(),
        name: formData.name,
        key: `pk_live_${Math.random().toString(36).substr(2, 20)}`,
        createdDate: new Date().toISOString().split('T')[0],
        lastUsed: 'Never',
        status: 'active',
        permissions: formData.permissions,
      };
      setApiKeys([newKey, ...apiKeys]);
      setFormData({ name: '', permissions: [], expiryDays: '' });
      setShowModal(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (confirm('Are you sure you want to revoke this key? This action cannot be undone.')) {
      // In a real app, call apiClient.delete(`/api/v1/settings/api-keys/${keyId}`);
      setApiKeys(
        apiKeys.map((key) =>
          key.id === keyId ? { ...key, status: 'revoked' as const } : key
        )
      );
    }
  };

  const handleDeleteKey = async (keyId: string) => {
    if (
      confirm(
        'Are you sure you want to permanently delete this key? This action cannot be undone.'
      )
    ) {
      // In a real app, call apiClient.delete(`/api/v1/settings/api-keys/${keyId}`);
      setApiKeys(apiKeys.filter((key) => key.id !== keyId));
    }
  };

  const handleTestWebhook = async (webhookId: string) => {
    alert(`Testing webhook ${webhookId}. Check your webhook endpoint logs.`);
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5 },
    },
  };

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 p-8"
    >
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <motion.div variants={itemVariants} className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-2">
              Developer & API Keys
            </h1>
            <p className="text-slate-600 dark:text-slate-400">
              Manage your API keys and webhooks for integrations
            </p>
          </div>
          <Button
            onClick={() => setShowModal(true)}
            className="bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700"
          >
            <Plus className="w-4 h-4 mr-2" />
            Generate New Key
          </Button>
        </motion.div>

        {/* Stats Cards */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                API Calls (24h)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">12,453</div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">↑ 8.2% from yesterday</p>
            </CardContent>
          </Card>

          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400 flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Avg Latency
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">48ms</div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Excellent performance</p>
            </CardContent>
          </Card>

          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400 flex items-center gap-2">
                <Zap className="w-4 h-4" />
                Rate Limit Usage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">34%</div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">Well within limits</p>
            </CardContent>
          </Card>

          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400 flex items-center gap-2">
                <Shield className="w-4 h-4" />
                Active Keys
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-slate-900 dark:text-white">3</div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">1 revoked key</p>
            </CardContent>
          </Card>
        </motion.div>

        {/* API Keys Section */}
        <motion.div variants={itemVariants} className="mb-8">
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Code2 className="w-5 h-5" />
                API Keys
              </CardTitle>
              <CardDescription>
                Your API keys for authenticating requests. Keep them secret and secure.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Name
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Key
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Created
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Last Used
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Status
                      </th>
                      <th className="text-left py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Permissions
                      </th>
                      <th className="text-right py-3 px-4 font-semibold text-slate-900 dark:text-white">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiKeys.map((key, index) => (
                      <motion.tr
                        key={key.id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="border-b border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                      >
                        <td className="py-3 px-4">
                          <span className="font-medium text-slate-900 dark:text-white">{key.name}</span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-slate-900 dark:text-white">
                              {revealedKeys[key.id] ? key.key : maskApiKey(key.key)}
                            </code>
                            <button
                              onClick={() => toggleRevealKey(key.id)}
                              className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                            >
                              {revealedKeys[key.id] ? (
                                <EyeOff className="w-4 h-4" />
                              ) : (
                                <Eye className="w-4 h-4" />
                              )}
                            </button>
                            <button
                              onClick={() => handleCopyKey(key.key, key.id)}
                              className={`transition-colors ${
                                copiedKey === key.id
                                  ? 'text-green-600 dark:text-green-400'
                                  : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                              }`}
                            >
                              {copiedKey === key.id ? (
                                <Check className="w-4 h-4" />
                              ) : (
                                <Copy className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                          {key.createdDate}
                        </td>
                        <td className="py-3 px-4 text-slate-600 dark:text-slate-400">
                          {key.lastUsed}
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            className={
                              key.status === 'active'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                            }
                          >
                            {key.status === 'active' ? (
                              <CheckCheck className="w-3 h-3 mr-1 inline" />
                            ) : (
                              <X className="w-3 h-3 mr-1 inline" />
                            )}
                            {key.status.charAt(0).toUpperCase() + key.status.slice(1)}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-wrap gap-1">
                            {key.permissions.slice(0, 2).map((perm) => (
                              <Badge
                                key={perm}
                                className="bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-300 text-xs"
                              >
                                {perm.split(' ')[0]}
                              </Badge>
                            ))}
                            {key.permissions.length > 2 && (
                              <Badge className="bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-300 text-xs">
                                +{key.permissions.length - 2}
                              </Badge>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex justify-end gap-2">
                            {key.status === 'active' && (
                              <button
                                onClick={() => handleRevokeKey(key.id)}
                                className="text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300 p-1 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded"
                              >
                                <RotateCcw className="w-4 h-4" />
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteKey(key.id)}
                              className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 p-1 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* API Usage Chart */}
        <motion.div variants={itemVariants} className="mb-8">
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader>
              <CardTitle>API Usage (Last 30 Days)</CardTitle>
              <CardDescription>Calls and average response latency over time</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={mockUsageData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" className="dark:stroke-slate-700" />
                  <XAxis dataKey="date" stroke="#94a3b8" className="dark:stroke-slate-600" />
                  <YAxis stroke="#94a3b8" className="dark:stroke-slate-600" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="calls"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ fill: '#3b82f6', r: 4 }}
                    activeDot={{ r: 6 }}
                    name="API Calls"
                  />
                  <Line
                    type="monotone"
                    dataKey="latency"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={{ fill: '#8b5cf6', r: 4 }}
                    activeDot={{ r: 6 }}
                    name="Latency (ms)"
                    yAxisId="right"
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        {/* Rate Limits Section */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertCircle className="w-5 h-5" />
                Rate Limits
              </CardTitle>
              <CardDescription>Current usage vs. endpoint limits</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {mockRateLimits.map((limit, index) => (
                  <motion.div
                    key={limit.endpoint}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium text-slate-900 dark:text-white">
                        {limit.endpoint}
                      </span>
                      <span className="text-sm text-slate-600 dark:text-slate-400">
                        {limit.current}/{parseInt(limit.limit)}
                      </span>
                    </div>
                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${limit.percentage}%` }}
                        transition={{ delay: index * 0.1, duration: 0.5 }}
                        className={`h-2 rounded-full ${
                          limit.percentage > 80
                            ? 'bg-red-500'
                            : limit.percentage > 60
                              ? 'bg-amber-500'
                              : 'bg-green-500'
                        }`}
                      />
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Code Snippets */}
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Code2 className="w-5 h-5" />
                Quick Start
              </CardTitle>
              <CardDescription>Example API calls in your favorite language</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-4">
                {(['curl', 'python', 'nodejs', 'php'] as const).map((lang) => (
                  <button
                    key={lang}
                    onClick={() => setActiveCodeTab(lang)}
                    className={`px-3 py-1 text-sm rounded transition-colors ${
                      activeCodeTab === lang
                        ? 'bg-blue-600 text-white dark:bg-blue-600'
                        : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
                    }`}
                  >
                    {lang.toUpperCase()}
                  </button>
                ))}
              </div>
              <pre className="bg-slate-100 dark:bg-slate-800 p-3 rounded text-xs overflow-x-auto text-slate-900 dark:text-slate-100">
                {codeSnippets[activeCodeTab]}
              </pre>
              <Button
                variant="outline"
                className="mt-4 w-full dark:border-slate-700 dark:hover:bg-slate-800"
                onClick={() => navigator.clipboard.writeText(codeSnippets[activeCodeTab])}
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy Code
              </Button>
            </CardContent>
          </Card>
        </motion.div>

        {/* Webhooks Section */}
        <motion.div variants={itemVariants} className="mb-8">
          <Card className="border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Webhook className="w-5 h-5" />
                Webhooks
              </CardTitle>
              <CardDescription>Manage webhook endpoints and subscriptions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {webhooks.map((webhook, index) => (
                  <motion.div
                    key={webhook.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="border border-slate-200 dark:border-slate-700 rounded-lg p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  >
                    <div className="flex justify-between items-start mb-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <code className="text-sm bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded text-slate-900 dark:text-white break-all">
                            {webhook.url}
                          </code>
                          <Badge
                            className={
                              webhook.status === 'active'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-400'
                            }
                          >
                            {webhook.status === 'active' ? (
                              <CheckCheck className="w-3 h-3 mr-1 inline" />
                            ) : (
                              <X className="w-3 h-3 mr-1 inline" />
                            )}
                            {webhook.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-slate-600 dark:text-slate-400 mb-2">
                          Last delivery: {webhook.lastDelivery} ({webhook.deliveryRate}% success rate)
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {webhook.events.map((event) => (
                            <Badge
                              key={event}
                              className="bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-300 text-xs"
                            >
                              {event}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div className="flex gap-2 ml-4">
                        <button
                          onClick={() => handleTestWebhook(webhook.id)}
                          className="text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 p-2 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                        >
                          <Zap className="w-4 h-4" />
                        </button>
                        <button className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded">
                          <RotateCcw className="w-4 h-4" />
                        </button>
                        <button className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
              <Button className="mt-4 w-full bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700">
                <Plus className="w-4 h-4 mr-2" />
                Add Webhook
              </Button>
            </CardContent>
          </Card>
        </motion.div>

        {/* Generate Key Modal */}
        {showModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6"
            >
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-4">
                Generate New API Key
              </h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-900 dark:text-white mb-2">
                    Key Name *
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Production API Key"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-500 dark:placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-900 dark:text-white mb-2">
                    Permissions *
                  </label>
                  <div className="space-y-2">
                    {[
                      'Read Conversations',
                      'Write Messages',
                      'Manage Contacts',
                      'Analytics',
                      'Billing Read-only',
                      'Webhooks',
                    ].map((perm) => (
                      <label key={perm} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.permissions.includes(perm)}
                          onChange={() => handlePermissionToggle(perm)}
                          className="w-4 h-4 rounded border-slate-300 dark:border-slate-600 text-blue-600 dark:bg-slate-700"
                        />
                        <span className="text-sm text-slate-700 dark:text-slate-300">{perm}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-900 dark:text-white mb-2">
                    Expiry (Optional)
                  </label>
                  <select
                    value={formData.expiryDays}
                    onChange={(e) => setFormData({ ...formData, expiryDays: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">No expiry</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="180">180 days</option>
                    <option value="365">1 year</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <Button
                  variant="outline"
                  onClick={() => setShowModal(false)}
                  className="flex-1 dark:border-slate-700 dark:hover:bg-slate-800"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateKey}
                  disabled={isLoading}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700"
                >
                  {isLoading ? 'Creating...' : 'Create Key'}
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
