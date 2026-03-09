// @ts-nocheck
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShoppingBag, Store, Globe, Link2, Unlink, RefreshCw, CheckCircle2,
  XCircle, Loader2, ExternalLink, AlertTriangle, Copy, Eye, EyeOff,
  ArrowRight, Clock, Package, ShoppingCart, Users,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Modal, ModalFooter } from '@/components/ui/Modal';
import { useAuthStore } from '@/stores/auth';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface StoreConnection {
  id: string;
  platform: 'shopify' | 'woocommerce' | 'custom';
  store_url: string;
  store_name: string;
  status: 'active' | 'disconnected' | 'error';
  last_sync_at: string | null;
  products_count?: number;
  orders_count?: number;
  customers_count?: number;
  created_at: string;
}

interface StoreConfig {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  authType: 'oauth' | 'manual';
  features: string[];
  setupTime: string;
  docsUrl?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Store Platform Configs (Shopify + WooCommerce + Custom — MVP only)
// ─────────────────────────────────────────────────────────────────────────────

const STORE_CONFIGS: StoreConfig[] = [
  {
    id: 'shopify',
    name: 'Shopify',
    description: 'Connect your Shopify store to sync products, orders, and customers. Supports Shopify Plus.',
    icon: <ShoppingBag className="w-8 h-8" />,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
    authType: 'oauth',
    features: ['Product sync', 'Order tracking', 'Customer import', 'Cart abandonment', 'Inventory alerts'],
    setupTime: '2 minutes',
    docsUrl: 'https://docs.partython.in/integrations/shopify',
  },
  {
    id: 'woocommerce',
    name: 'WooCommerce',
    description: 'Connect your WooCommerce (WordPress) store. Works with any self-hosted WordPress + WooCommerce setup.',
    icon: <ShoppingCart className="w-8 h-8" />,
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-900/20',
    authType: 'oauth',
    features: ['Product sync', 'Order tracking', 'Customer import', 'Webhook events', 'REST API v3'],
    setupTime: '3 minutes',
    docsUrl: 'https://docs.partython.in/integrations/woocommerce',
  },
  {
    id: 'custom',
    name: 'Custom Store',
    description: 'Connect any e-commerce platform using API keys. Works with self-hosted stores, headless commerce, or custom builds.',
    icon: <Globe className="w-8 h-8" />,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
    authType: 'manual',
    features: ['REST API connector', 'Custom field mapping', 'Webhook support', 'Any platform'],
    setupTime: '5 minutes',
    docsUrl: 'https://docs.partython.in/integrations/custom-store',
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export default function MarketplacePage() {
  const token = useAuthStore((state) => state.token);

  // State
  const [connections, setConnections] = useState<StoreConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null);
  const [testingConnection, setTestingConnection] = useState<string | null>(null);
  const [syncingConnection, setSyncingConnection] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);

  // Modals
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState<StoreConfig | null>(null);
  const [showCustomModal, setShowCustomModal] = useState(false);

  // Form fields
  const [shopifyDomain, setShopifyDomain] = useState('');
  const [wcStoreUrl, setWcStoreUrl] = useState('');
  const [customStoreUrl, setCustomStoreUrl] = useState('');
  const [customApiKey, setCustomApiKey] = useState('');
  const [customApiSecret, setCustomApiSecret] = useState('');
  const [customStoreName, setCustomStoreName] = useState('');
  const [showSecrets, setShowSecrets] = useState(false);

  // Notifications
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // ─────────────────────────────────────────────────────────────────────────
  // Fetch connected stores
  // ─────────────────────────────────────────────────────────────────────────

  const fetchConnections = useCallback(async () => {
    if (!token) return;
    try {
      const resp = await fetch('/api/ecommerce/stores', {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const data = await resp.json();
      setConnections(data.connections || []);
    } catch (error) {
      console.error('Failed to fetch store connections:', error);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // Check URL params for OAuth callback results
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    const status = params.get('status');

    if (connected && status) {
      if (status === 'success') {
        showToast('success', `${connected.charAt(0).toUpperCase() + connected.slice(1)} store connected successfully!`);
        fetchConnections();
      } else {
        const reason = params.get('reason') || 'unknown';
        showToast('error', `Failed to connect ${connected}: ${reason}`);
      }
      // Clean URL
      window.history.replaceState({}, '', '/marketplace');
    }
  }, []);

  // ─────────────────────────────────────────────────────────────────────────
  // Actions
  // ─────────────────────────────────────────────────────────────────────────

  const showToast = (type: 'success' | 'error', message: string) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 5000);
  };

  const handleConnect = (platform: StoreConfig) => {
    setSelectedPlatform(platform);
    if (platform.authType === 'manual') {
      setShowCustomModal(true);
    } else {
      setShowConnectModal(true);
    }
  };

  const handleShopifyOAuth = async () => {
    if (!shopifyDomain) return;

    const domain = shopifyDomain.includes('.myshopify.com')
      ? shopifyDomain.trim().toLowerCase()
      : `${shopifyDomain.trim().toLowerCase()}.myshopify.com`;

    setConnectingPlatform('shopify');
    try {
      const resp = await fetch('/api/oauth/shopify', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ shop_domain: domain }),
      });

      const data = await resp.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        showToast('error', data.message || 'Failed to start Shopify OAuth');
      }
    } catch (error) {
      showToast('error', 'Failed to connect Shopify. Please try again.');
    } finally {
      setConnectingPlatform(null);
      setShowConnectModal(false);
    }
  };

  const handleWooCommerceOAuth = async () => {
    if (!wcStoreUrl) return;

    let url = wcStoreUrl.trim();
    if (!url.startsWith('http')) url = `https://${url}`;

    setConnectingPlatform('woocommerce');
    try {
      const resp = await fetch('/api/oauth/woocommerce', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ store_url: url }),
      });

      const data = await resp.json();
      if (data.auth_url) {
        window.location.href = data.auth_url;
      } else {
        showToast('error', data.message || 'Failed to start WooCommerce auth');
      }
    } catch (error) {
      showToast('error', 'Failed to connect WooCommerce. Please try again.');
    } finally {
      setConnectingPlatform(null);
      setShowConnectModal(false);
    }
  };

  const handleCustomConnect = async () => {
    if (!customStoreUrl || !customApiKey || !customApiSecret) return;

    let url = customStoreUrl.trim();
    if (!url.startsWith('http')) url = `https://${url}`;

    setConnectingPlatform('custom');
    try {
      const resp = await fetch('/api/ecommerce/stores', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: 'custom',
          store_url: url,
          api_key: customApiKey,
          api_secret: customApiSecret,
          metadata: {
            store_name: customStoreName || url,
          },
        }),
      });

      const data = await resp.json();
      if (resp.ok) {
        showToast('success', 'Custom store connected successfully!');
        fetchConnections();
        setShowCustomModal(false);
        resetCustomForm();
      } else {
        showToast('error', data.message || 'Failed to connect store');
      }
    } catch (error) {
      showToast('error', 'Failed to connect store. Please try again.');
    } finally {
      setConnectingPlatform(null);
    }
  };

  const handleTestConnection = async (connectionId: string) => {
    setTestingConnection(connectionId);
    try {
      const resp = await fetch('/api/ecommerce/test', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ connection_id: connectionId }),
      });

      const data = await resp.json();
      if (data.status === 'success') {
        showToast('success', data.message || 'Connection is healthy!');
      } else {
        showToast('error', data.message || 'Connection test failed');
      }
    } catch (error) {
      showToast('error', 'Connection test failed');
    } finally {
      setTestingConnection(null);
    }
  };

  const handleSync = async (connectionId: string) => {
    setSyncingConnection(connectionId);
    try {
      const resp = await fetch('/api/ecommerce/sync', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ connection_id: connectionId, sync_type: 'all' }),
      });

      const data = await resp.json();
      if (resp.ok) {
        showToast('success', 'Sync started! This may take a few minutes.');
        // Refresh after a short delay
        setTimeout(fetchConnections, 3000);
      } else {
        showToast('error', data.message || 'Sync failed');
      }
    } catch (error) {
      showToast('error', 'Failed to trigger sync');
    } finally {
      setSyncingConnection(null);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    if (!confirm('Are you sure you want to disconnect this store? Synced data will be preserved.')) return;

    setDisconnecting(connectionId);
    try {
      const resp = await fetch(`/api/ecommerce/stores?id=${connectionId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (resp.ok) {
        showToast('success', 'Store disconnected');
        setConnections(prev => prev.filter(c => c.id !== connectionId));
      } else {
        const data = await resp.json();
        showToast('error', data.message || 'Failed to disconnect');
      }
    } catch (error) {
      showToast('error', 'Failed to disconnect store');
    } finally {
      setDisconnecting(null);
    }
  };

  const resetCustomForm = () => {
    setCustomStoreUrl('');
    setCustomApiKey('');
    setCustomApiSecret('');
    setCustomStoreName('');
    setShowSecrets(false);
  };

  const getStoreConfig = (platform: string) => {
    return STORE_CONFIGS.find(c => c.id === platform);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge className="bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800">Active</Badge>;
      case 'error':
        return <Badge className="bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800">Error</Badge>;
      default:
        return <Badge className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">Disconnected</Badge>;
    }
  };

  const isAlreadyConnected = (platformId: string) => {
    return connections.some(c => c.platform === platformId && c.status === 'active');
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      {/* Toast Notification */}
      <AnimatePresence>
        {toast && (
          <motion.div
            className={`fixed top-4 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg ${
              toast.type === 'success'
                ? 'bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 text-green-800 dark:text-green-200'
                : 'bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-700 text-red-800 dark:text-red-200'
            }`}
            initial={{ opacity: 0, y: -20, x: 20 }}
            animate={{ opacity: 1, y: 0, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
          >
            {toast.type === 'success' ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
            <span className="text-sm font-medium">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <motion.div
        className="px-6 py-8 md:px-8"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <Store className="w-8 h-8 text-blue-600 dark:text-blue-400" />
            <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white">
              Store Connections
            </h1>
          </div>
          <p className="text-slate-600 dark:text-slate-400">
            Connect your e-commerce store to sync products, orders, and customer conversations
          </p>
        </div>
      </motion.div>

      {/* Connected Stores Section */}
      {connections.length > 0 && (
        <motion.div
          className="px-6 md:px-8 pb-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <div className="max-w-7xl mx-auto">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">
              Connected Stores ({connections.length})
            </h2>
            <div className="space-y-4">
              {connections.map((conn) => {
                const config = getStoreConfig(conn.platform);
                return (
                  <motion.div
                    key={conn.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    layout
                  >
                    <Card className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <CardContent className="py-5">
                        <div className="flex items-center justify-between gap-4 flex-wrap">
                          {/* Store info */}
                          <div className="flex items-center gap-4 min-w-0 flex-1">
                            <div className={`p-3 rounded-lg ${config?.bgColor || 'bg-slate-100 dark:bg-slate-700'}`}>
                              <span className={config?.color || 'text-slate-600'}>
                                {config?.icon || <Store className="w-8 h-8" />}
                              </span>
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <h3 className="font-semibold text-slate-900 dark:text-white truncate">
                                  {conn.store_name}
                                </h3>
                                {getStatusBadge(conn.status)}
                              </div>
                              <p className="text-sm text-slate-500 dark:text-slate-400 truncate">
                                {conn.store_url}
                              </p>
                              <div className="flex items-center gap-4 mt-2 text-xs text-slate-500 dark:text-slate-400">
                                {conn.products_count != null && (
                                  <span className="flex items-center gap-1">
                                    <Package size={12} /> {conn.products_count} products
                                  </span>
                                )}
                                {conn.orders_count != null && (
                                  <span className="flex items-center gap-1">
                                    <ShoppingCart size={12} /> {conn.orders_count} orders
                                  </span>
                                )}
                                {conn.customers_count != null && (
                                  <span className="flex items-center gap-1">
                                    <Users size={12} /> {conn.customers_count} customers
                                  </span>
                                )}
                                {conn.last_sync_at && (
                                  <span className="flex items-center gap-1">
                                    <Clock size={12} /> Last sync: {new Date(conn.last_sync_at).toLocaleDateString()}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Actions */}
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={testingConnection === conn.id}
                              onClick={() => handleTestConnection(conn.id)}
                              title="Test Connection"
                            >
                              {testingConnection === conn.id ? (
                                <Loader2 size={16} className="animate-spin" />
                              ) : (
                                <CheckCircle2 size={16} />
                              )}
                              <span className="hidden sm:inline ml-1">Test</span>
                            </Button>

                            <Button
                              size="sm"
                              variant="outline"
                              disabled={syncingConnection === conn.id}
                              onClick={() => handleSync(conn.id)}
                              title="Sync Data"
                            >
                              {syncingConnection === conn.id ? (
                                <Loader2 size={16} className="animate-spin" />
                              ) : (
                                <RefreshCw size={16} />
                              )}
                              <span className="hidden sm:inline ml-1">Sync</span>
                            </Button>

                            <Button
                              size="sm"
                              variant="outline"
                              className="text-red-500 hover:text-red-700 hover:border-red-300 dark:hover:border-red-700"
                              disabled={disconnecting === conn.id}
                              onClick={() => handleDisconnect(conn.id)}
                              title="Disconnect"
                            >
                              {disconnecting === conn.id ? (
                                <Loader2 size={16} className="animate-spin" />
                              ) : (
                                <Unlink size={16} />
                              )}
                              <span className="hidden sm:inline ml-1">Disconnect</span>
                            </Button>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </motion.div>
      )}

      {/* Available Platforms */}
      <motion.div
        className="px-6 md:px-8 py-8"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.2 }}
      >
        <div className="max-w-7xl mx-auto">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">
            Connect a Store
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
            Choose your e-commerce platform to get started
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {STORE_CONFIGS.map((config) => {
              const connected = isAlreadyConnected(config.id);
              return (
                <motion.div
                  key={config.id}
                  whileHover={{ translateY: -4 }}
                  transition={{ duration: 0.2 }}
                >
                  <Card className={`h-full bg-white dark:bg-slate-800 border-2 transition-all cursor-pointer ${
                    connected
                      ? 'border-green-200 dark:border-green-800'
                      : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 dark:hover:border-blue-700'
                  }`}>
                    <CardHeader>
                      <div className="flex items-center justify-between mb-4">
                        <div className={`p-3 rounded-lg ${config.bgColor}`}>
                          <span className={config.color}>{config.icon}</span>
                        </div>
                        {connected && (
                          <Badge className="bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                            Connected
                          </Badge>
                        )}
                      </div>
                      <CardTitle className="text-xl">{config.name}</CardTitle>
                      <CardDescription className="text-sm">
                        {config.description}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        {/* Features */}
                        <div className="flex flex-wrap gap-1.5">
                          {config.features.map((feature) => (
                            <span
                              key={feature}
                              className="text-xs px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400"
                            >
                              {feature}
                            </span>
                          ))}
                        </div>

                        {/* Setup time */}
                        <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
                          <Clock size={12} /> Setup: ~{config.setupTime}
                        </p>

                        {/* Connect button */}
                        <Button
                          className="w-full"
                          onClick={() => handleConnect(config)}
                          disabled={connectingPlatform === config.id}
                        >
                          {connectingPlatform === config.id ? (
                            <span className="flex items-center gap-2">
                              <Loader2 size={16} className="animate-spin" />
                              Connecting...
                            </span>
                          ) : connected ? (
                            <span className="flex items-center gap-2">
                              <Link2 size={16} />
                              Connect Another
                            </span>
                          ) : (
                            <span className="flex items-center gap-2">
                              <Link2 size={16} />
                              Connect {config.name}
                            </span>
                          )}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </div>
      </motion.div>

      {/* How It Works */}
      <motion.div
        className="px-6 md:px-8 py-8"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="max-w-7xl mx-auto">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-6">
            How Store Connections Work
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {[
              {
                step: '1',
                title: 'Connect Store',
                desc: 'Authorize access to your e-commerce platform via OAuth or API keys',
                icon: <Link2 className="w-6 h-6" />,
              },
              {
                step: '2',
                title: 'Auto Sync',
                desc: 'Products, orders, and customer data sync automatically via webhooks',
                icon: <RefreshCw className="w-6 h-6" />,
              },
              {
                step: '3',
                title: 'AI Conversations',
                desc: 'Your AI bot answers product questions, tracks orders, and handles returns',
                icon: <Store className="w-6 h-6" />,
              },
              {
                step: '4',
                title: 'Recover Sales',
                desc: 'Abandoned cart alerts and automated follow-ups recover lost revenue',
                icon: <ShoppingBag className="w-6 h-6" />,
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center mx-auto mb-3">
                  {item.icon}
                </div>
                <h3 className="font-semibold text-slate-900 dark:text-white mb-1">{item.title}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* ─── Shopify / WooCommerce OAuth Connect Modal ─── */}
      <Modal
        isOpen={showConnectModal}
        onClose={() => { setShowConnectModal(false); setSelectedPlatform(null); }}
        title={`Connect ${selectedPlatform?.name || 'Store'}`}
        size="lg"
      >
        {selectedPlatform?.id === 'shopify' && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Enter your Shopify store domain to authorize access. You'll be redirected to Shopify to approve permissions.
            </p>
            <Input
              label="Shopify Store Domain"
              placeholder="yourstore.myshopify.com"
              value={shopifyDomain}
              onChange={(e) => setShopifyDomain(e.target.value)}
              helperText="Your .myshopify.com domain (e.g., acmeshop or acmeshop.myshopify.com)"
            />
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  You'll be redirected to Shopify to authorize access. We request read access to customers, orders, and products. Your store credentials are encrypted and never stored in plain text.
                </p>
              </div>
            </div>
            <ModalFooter>
              <Button variant="outline" onClick={() => setShowConnectModal(false)}>Cancel</Button>
              <Button
                onClick={handleShopifyOAuth}
                disabled={!shopifyDomain || connectingPlatform === 'shopify'}
              >
                {connectingPlatform === 'shopify' ? (
                  <span className="flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin" /> Redirecting...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <ExternalLink size={16} /> Authorize on Shopify
                  </span>
                )}
              </Button>
            </ModalFooter>
          </div>
        )}

        {selectedPlatform?.id === 'woocommerce' && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Enter your WooCommerce store URL. You'll be redirected to your store to approve REST API access.
            </p>
            <Input
              label="Store URL"
              placeholder="https://mystore.com"
              value={wcStoreUrl}
              onChange={(e) => setWcStoreUrl(e.target.value)}
              helperText="Your WordPress/WooCommerce site URL (must have WooCommerce REST API enabled)"
            />
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <AlertTriangle size={16} className="text-blue-600 dark:text-blue-400 mt-0.5 shrink-0" />
                <div className="text-xs text-blue-700 dark:text-blue-300 space-y-1">
                  <p>Requirements for WooCommerce connection:</p>
                  <p>1. WooCommerce plugin must be installed and active</p>
                  <p>2. WordPress REST API must be accessible (not blocked by security plugins)</p>
                  <p>3. SSL certificate recommended (HTTPS)</p>
                </div>
              </div>
            </div>
            <ModalFooter>
              <Button variant="outline" onClick={() => setShowConnectModal(false)}>Cancel</Button>
              <Button
                onClick={handleWooCommerceOAuth}
                disabled={!wcStoreUrl || connectingPlatform === 'woocommerce'}
              >
                {connectingPlatform === 'woocommerce' ? (
                  <span className="flex items-center gap-2">
                    <Loader2 size={16} className="animate-spin" /> Redirecting...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <ExternalLink size={16} /> Authorize on WooCommerce
                  </span>
                )}
              </Button>
            </ModalFooter>
          </div>
        )}
      </Modal>

      {/* ─── Custom Store Manual Connect Modal ─── */}
      <Modal
        isOpen={showCustomModal}
        onClose={() => { setShowCustomModal(false); resetCustomForm(); }}
        title="Connect Custom Store"
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Enter your store's API credentials. Your bot will use these to fetch products, orders, and customer data.
          </p>

          <Input
            label="Store Name"
            placeholder="My Custom Store"
            value={customStoreName}
            onChange={(e) => setCustomStoreName(e.target.value)}
            helperText="A friendly name to identify this store"
          />

          <Input
            label="Store URL"
            placeholder="https://api.mystore.com"
            value={customStoreUrl}
            onChange={(e) => setCustomStoreUrl(e.target.value)}
            required
            helperText="Base URL for your store's API"
          />

          <Input
            label="API Key"
            placeholder="pk_live_xxxxxxxxxx"
            value={customApiKey}
            onChange={(e) => setCustomApiKey(e.target.value)}
            required
          />

          <div className="relative">
            <Input
              label="API Secret"
              type={showSecrets ? 'text' : 'password'}
              placeholder="sk_live_xxxxxxxxxx"
              value={customApiSecret}
              onChange={(e) => setCustomApiSecret(e.target.value)}
              required
            />
            <button
              type="button"
              className="absolute right-3 top-9 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              onClick={() => setShowSecrets(!showSecrets)}
            >
              {showSecrets ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          <div className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Your store API should support these endpoints:
            </h4>
            <div className="text-xs text-slate-500 dark:text-slate-400 space-y-1 font-mono">
              <p>GET /products — List products</p>
              <p>GET /orders — List orders</p>
              <p>GET /customers — List customers</p>
              <p>POST /webhooks — Register webhook events</p>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              After connecting, you can configure custom field mappings in the store settings.
            </p>
          </div>

          <ModalFooter>
            <Button variant="outline" onClick={() => { setShowCustomModal(false); resetCustomForm(); }}>
              Cancel
            </Button>
            <Button
              onClick={handleCustomConnect}
              disabled={!customStoreUrl || !customApiKey || !customApiSecret || connectingPlatform === 'custom'}
            >
              {connectingPlatform === 'custom' ? (
                <span className="flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" /> Connecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Link2 size={16} /> Connect Store
                </span>
              )}
            </Button>
          </ModalFooter>
        </div>
      </Modal>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      )}
    </div>
  );
}
