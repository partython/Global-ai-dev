/**
 * Priya AI Chat Widget
 * Embeddable JavaScript widget for tenant websites.
 * Installation: <script src="https://cdn.priyaai.com/widget/chat-widget.js" data-tenant="tenant-slug"></script>
 */

(function () {
  'use strict';

  // ========================================================================
  // Configuration & Constants
  // ========================================================================

  const DEFAULT_CONFIG = {
    apiUrl: 'https://api.priyaai.com',
    wsUrl: 'wss://api.priyaai.com',
    position: 'bottom-right',
    primaryColor: '#6366f1',
    secondaryColor: '#4f46e5',
    widgetName: 'Priya AI Sales',
    greeting: 'Hi! How can we help you today?',
    placeholder: 'Type your message...',
    enableSound: true,
    showPoweredBy: true,
    useWebSocket: true,
    fallbackToRest: true,
  };

  // ========================================================================
  // Utility Functions
  // ========================================================================

  function log(message, data = null) {
    if (window.__PRIYA_DEBUG__) {
      console.log(`[PriyaWidget] ${message}`, data || '');
    }
  }

  function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getVisitorFingerprint() {
    const userAgent = navigator.userAgent;
    const screen = `${window.screen.width}x${window.screen.height}`;
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const fingerprint = `${userAgent}:${screen}:${timezone}`;
    return hashSimple(fingerprint);
  }

  function hashSimple(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = (hash << 5) - hash + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  }

  function getUTMParams() {
    const params = new URLSearchParams(window.location.search);
    return {
      utm_source: params.get('utm_source') || null,
      utm_medium: params.get('utm_medium') || null,
      utm_campaign: params.get('utm_campaign') || null,
    };
  }

  function getSessionId() {
    const stored = localStorage.getItem('priya_session_id');
    if (stored) {
      log('Using stored session ID', stored);
      return stored;
    }
    const newId = generateUUID();
    localStorage.setItem('priya_session_id', newId);
    return newId;
  }

  function saveVisitorInfo(name, email, phone) {
    const info = { name, email, phone };
    sessionStorage.setItem('priya_visitor_info', JSON.stringify(info));
  }

  function getVisitorInfo() {
    const stored = sessionStorage.getItem('priya_visitor_info');
    return stored ? JSON.parse(stored) : { name: null, email: null, phone: null };
  }

  // ========================================================================
  // Priya Widget Class
  // ========================================================================

  class PriyaWidget {
    constructor(tenantSlug, customConfig = {}) {
      this.tenantSlug = tenantSlug;
      this.sessionId = getSessionId();
      this.config = { ...DEFAULT_CONFIG, ...customConfig };
      this.widgetConfig = null;
      this.websocket = null;
      this.messages = [];
      this.isOpen = false;
      this.isConnected = false;
      this.typingTimeout = null;
      this.formSubmitted = false;
      this.iframeDom = null;

      log('Initializing widget for tenant', tenantSlug);
      this.init();
    }

    // Initialize widget
    async init() {
      try {
        // Load tenant widget config
        await this.loadWidgetConfig();

        // Create session on backend
        await this.createSession();

        // Inject CSS
        this.injectStyles();

        // Create widget DOM
        this.createWidgetDOM();

        // Load proactive triggers
        if (this.widgetConfig?.enable_proactive_triggers) {
          this.loadProactiveTriggers();
        }

        log('Widget initialized successfully');
      } catch (error) {
        console.error('[PriyaWidget] Initialization failed:', error);
      }
    }

    // Load widget configuration from backend
    async loadWidgetConfig() {
      try {
        const response = await fetch(
          `${this.config.apiUrl}/api/v1/widget/config/${this.tenantSlug}`
        );

        if (!response.ok) {
          throw new Error(`Config load failed: ${response.status}`);
        }

        this.widgetConfig = await response.json();
        log('Widget config loaded', this.widgetConfig);

        // Apply custom config
        Object.keys(this.widgetConfig).forEach((key) => {
          const configKey = key.replace(/_([a-z])/g, (g) => g[1].toUpperCase());
          if (DEFAULT_CONFIG.hasOwnProperty(configKey)) {
            this.config[configKey] = this.widgetConfig[key];
          }
        });
      } catch (error) {
        console.error('[PriyaWidget] Failed to load config:', error);
        this.widgetConfig = {};
      }
    }

    // Create chat session on backend
    async createSession() {
      try {
        const utmParams = getUTMParams();
        const payload = {
          page_url: window.location.href,
          referrer: document.referrer || null,
          utm_source: utmParams.utm_source,
          utm_medium: utmParams.utm_medium,
          utm_campaign: utmParams.utm_campaign,
          user_agent: navigator.userAgent,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          ip_address: null, // Will be set by backend via request IP
          visitor_fingerprint: getVisitorFingerprint(),
        };

        const response = await fetch(`${this.config.apiUrl}/api/v1/sessions/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (response.ok) {
          const data = await response.json();
          this.sessionId = data.session_id;
          localStorage.setItem('priya_session_id', this.sessionId);
          log('Session created', this.sessionId);
        }
      } catch (error) {
        console.error('[PriyaWidget] Failed to create session:', error);
      }
    }

    // Connect WebSocket
    connectWebSocket() {
      if (this.isConnected) return;

      try {
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${this.config.wsUrl.replace(/^https?:/, protocol)}/ws/${this.sessionId}`;

        log('Connecting WebSocket', url);
        this.websocket = new WebSocket(url);

        this.websocket.onopen = () => {
          log('WebSocket connected');
          this.isConnected = true;
          this.sendWelcome();
        };

        this.websocket.onmessage = (event) => {
          this.handleMessage(JSON.parse(event.data));
        };

        this.websocket.onclose = () => {
          log('WebSocket disconnected');
          this.isConnected = false;
          if (this.config.fallbackToRest) {
            log('Falling back to REST API');
          }
        };

        this.websocket.onerror = (error) => {
          console.error('[PriyaWidget] WebSocket error:', error);
          this.isConnected = false;
        };
      } catch (error) {
        console.error('[PriyaWidget] WebSocket connection failed:', error);
        this.isConnected = false;
      }
    }

    // Handle incoming WebSocket message
    handleMessage(message) {
      const type = message.type;

      switch (type) {
        case 'connection':
          log('Connected to chat service');
          break;

        case 'message':
          this.displayMessage(message.sender, message.content, message.timestamp);
          break;

        case 'typing':
          this.displayTypingIndicator(message.is_typing);
          break;

        case 'ping':
          if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({ type: 'pong' }));
          }
          break;

        case 'error':
          console.error('[PriyaWidget]', message.error);
          break;

        default:
          log('Unknown message type', type);
      }
    }

    // Send welcome message on connection
    sendWelcome() {
      const visitorInfo = getVisitorInfo();
      if (this.isConnected && !this.formSubmitted) {
        const msg = {
          type: 'message',
          content: 'Hello! I just connected to the chat.',
          visitor_name: visitorInfo.name,
          visitor_email: visitorInfo.email,
          visitor_phone: visitorInfo.phone,
        };
        this.websocket.send(JSON.stringify(msg));
        this.formSubmitted = true;
      }
    }

    // Send message via WebSocket or REST
    async sendMessage(content) {
      if (!content.trim()) return;

      const visitorInfo = getVisitorInfo();

      // Display visitor message immediately
      this.displayMessage('visitor', content);

      if (this.isConnected && this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        // Use WebSocket
        const message = {
          type: 'message',
          content: content,
          visitor_name: visitorInfo.name,
          visitor_email: visitorInfo.email,
          visitor_phone: visitorInfo.phone,
        };
        this.websocket.send(JSON.stringify(message));
        log('Message sent via WebSocket');
      } else {
        // Use REST fallback
        try {
          const response = await fetch(`${this.config.apiUrl}/api/v1/chat/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: this.sessionId,
              content: content,
              visitor_name: visitorInfo.name,
              visitor_email: visitorInfo.email,
              visitor_phone: visitorInfo.phone,
            }),
          });

          if (response.ok) {
            const data = await response.json();
            this.displayMessage('ai', data.content, data.timestamp);
            log('Message sent via REST');
          }
        } catch (error) {
          console.error('[PriyaWidget] Failed to send message:', error);
          this.displayMessage('ai', 'Sorry, there was an error. Please try again.');
        }
      }
    }

    // Display message in chat window
    displayMessage(sender, content, timestamp = null) {
      if (!this.iframeDom) return;

      const messagesDiv = this.iframeDom.querySelector('.priya-messages');
      if (!messagesDiv) return;

      const messageEl = document.createElement('div');
      messageEl.className = `priya-message priya-message-${sender}`;

      const contentEl = document.createElement('div');
      contentEl.className = 'priya-message-content';
      contentEl.textContent = content;

      messageEl.appendChild(contentEl);

      if (timestamp) {
        const timeEl = document.createElement('div');
        timeEl.className = 'priya-message-time';
        timeEl.textContent = new Date(timestamp).toLocaleTimeString();
        messageEl.appendChild(timeEl);
      }

      messagesDiv.appendChild(messageEl);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;

      // Play sound if enabled and sender is AI
      if (this.config.enableSound && sender === 'ai') {
        this.playNotificationSound();
      }
    }

    // Display typing indicator
    displayTypingIndicator(isTyping) {
      if (!this.iframeDom) return;

      const messagesDiv = this.iframeDom.querySelector('.priya-messages');
      const existingTyping = messagesDiv?.querySelector('.priya-typing-indicator');

      if (isTyping && !existingTyping) {
        const typingEl = document.createElement('div');
        typingEl.className = 'priya-typing-indicator';
        typingEl.innerHTML = '<span></span><span></span><span></span>';
        messagesDiv.appendChild(typingEl);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      } else if (!isTyping && existingTyping) {
        existingTyping.remove();
      }
    }

    // Send typing indicator
    sendTypingIndicator(isTyping) {
      if (this.isConnected && this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.send(
          JSON.stringify({
            type: 'typing',
            is_typing: isTyping,
          })
        );
      }
    }

    // Play notification sound
    playNotificationSound() {
      // Use Web Audio API to generate a beep
      try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();

        oscillator.connect(gain);
        gain.connect(audioContext.destination);

        oscillator.frequency.value = 800;
        oscillator.type = 'sine';

        gain.gain.setValueAtTime(0.3, audioContext.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.1);
      } catch (e) {
        log('Audio notification not available');
      }
    }

    // Load proactive triggers
    async loadProactiveTriggers() {
      try {
        const response = await fetch(
          `${this.config.apiUrl}/api/v1/triggers/${this.tenantSlug}`
        );

        if (response.ok) {
          const data = await response.json();
          this.triggers = data.triggers || [];
          this.setupTriggers();
          log('Triggers loaded', this.triggers);
        }
      } catch (error) {
        console.error('[PriyaWidget] Failed to load triggers:', error);
      }
    }

    // Setup proactive trigger listeners
    setupTriggers() {
      if (!this.triggers || this.triggers.length === 0) return;

      this.triggers.forEach((trigger) => {
        if (trigger.trigger_type === 'time_on_page') {
          setTimeout(() => {
            this.showProactiveTrigger(trigger);
          }, trigger.trigger_delay_seconds * 1000);
        } else if (trigger.trigger_type === 'scroll_depth') {
          window.addEventListener('scroll', () => {
            const scrollPercentage = (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100;
            if (scrollPercentage > 50) {
              this.showProactiveTrigger(trigger);
            }
          });
        } else if (trigger.trigger_type === 'exit_intent') {
          document.addEventListener('mouseleave', () => {
            this.showProactiveTrigger(trigger);
          });
        }
      });
    }

    // Show proactive trigger message
    showProactiveTrigger(trigger) {
      if (this.isOpen) return;

      const notification = document.createElement('div');
      notification.className = 'priya-notification';
      notification.style.backgroundColor = this.config.primaryColor;
      notification.innerHTML = `
        <div class="priya-notification-content">
          <p>${trigger.trigger_message}</p>
          <button class="priya-notification-close">×</button>
        </div>
      `;

      document.body.appendChild(notification);

      notification.querySelector('.priya-notification-close').onclick = () => {
        notification.remove();
      };

      setTimeout(() => {
        notification.remove();
      }, 10000);
    }

    // Show pre-chat form
    showPrechatForm() {
      if (!this.widgetConfig?.require_prechat_form || this.formSubmitted) {
        this.connectWebSocket();
        return;
      }

      const form = document.createElement('div');
      form.className = 'priya-form';
      form.innerHTML = `
        <div class="priya-form-content">
          <h3>Before we chat</h3>
          ${this.widgetConfig.prechat_fields.includes('name') ? '<input type="text" placeholder="Your name" class="priya-form-input" id="priya-name">' : ''}
          ${this.widgetConfig.prechat_fields.includes('email') ? '<input type="email" placeholder="Your email" class="priya-form-input" id="priya-email">' : ''}
          ${this.widgetConfig.prechat_fields.includes('phone') ? '<input type="tel" placeholder="Your phone" class="priya-form-input" id="priya-phone">' : ''}
          <button class="priya-form-submit">Start Chat</button>
          ${this.widgetConfig.allow_anonymous_chat ? '<button class="priya-form-skip">Skip</button>' : ''}
        </div>
      `;

      const messagesDiv = this.iframeDom.querySelector('.priya-messages');
      messagesDiv.appendChild(form);

      form.querySelector('.priya-form-submit').onclick = () => {
        const name = this.iframeDom.querySelector('#priya-name')?.value || '';
        const email = this.iframeDom.querySelector('#priya-email')?.value || '';
        const phone = this.iframeDom.querySelector('#priya-phone')?.value || '';

        saveVisitorInfo(name, email, phone);
        this.formSubmitted = true;
        form.remove();
        this.connectWebSocket();
      };

      if (this.widgetConfig.allow_anonymous_chat) {
        form.querySelector('.priya-form-skip').onclick = () => {
          this.formSubmitted = true;
          form.remove();
          this.connectWebSocket();
        };
      }
    }

    // Create widget DOM elements
    createWidgetDOM() {
      // Create bubble button
      const bubble = document.createElement('div');
      bubble.className = `priya-bubble priya-position-${this.config.position}`;
      bubble.innerHTML = `
        <button class="priya-bubble-button" style="background-color: ${this.config.primaryColor}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        </button>
        <div class="priya-badge" style="display: none;">1</div>
      `;

      document.body.appendChild(bubble);

      // Create modal with iframe for CSS isolation
      const modal = document.createElement('div');
      modal.className = `priya-modal priya-position-${this.config.position}`;
      modal.innerHTML = `
        <iframe class="priya-iframe" allow="microphone; camera" sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals"></iframe>
      `;
      document.body.appendChild(modal);

      // Get iframe document
      const iframe = modal.querySelector('iframe');
      this.iframeDom = iframe.contentDocument || iframe.contentWindow.document;

      // Inject styles into iframe
      const style = this.iframeDom.createElement('style');
      style.textContent = this.getIframeStyles();
      this.iframeDom.head.appendChild(style);

      // Create chat container in iframe
      const container = this.iframeDom.createElement('div');
      container.className = 'priya-container';
      container.innerHTML = `
        <div class="priya-header" style="background-color: ${this.config.primaryColor}">
          <h3>${this.widgetConfig?.widget_name || this.config.widgetName}</h3>
          <button class="priya-close-btn">×</button>
        </div>
        <div class="priya-messages"></div>
        <div class="priya-input-area">
          <input type="text" class="priya-input" placeholder="${this.config.placeholder}" />
          <button class="priya-send-btn" style="background-color: ${this.config.primaryColor}">→</button>
        </div>
        <div class="priya-powered-by" style="display: ${this.config.showPoweredBy ? 'block' : 'none'}">
          Powered by <a href="https://priyaai.com" target="_blank">Priya AI</a>
        </div>
      `;
      this.iframeDom.body.appendChild(container);

      // Event listeners
      const bubbleBtn = bubble.querySelector('.priya-bubble-button');
      bubbleBtn.onclick = () => this.toggleModal(bubble, modal);

      const closeBtn = this.iframeDom.querySelector('.priya-close-btn');
      closeBtn.onclick = () => this.toggleModal(bubble, modal);

      const input = this.iframeDom.querySelector('.priya-input');
      const sendBtn = this.iframeDom.querySelector('.priya-send-btn');

      input.onkeypress = (e) => {
        if (e.key === 'Enter') {
          this.sendMessage(input.value);
          input.value = '';
        }
      };

      input.oninput = () => {
        if (input.value.trim()) {
          this.sendTypingIndicator(true);
          if (this.typingTimeout) clearTimeout(this.typingTimeout);
          this.typingTimeout = setTimeout(() => {
            this.sendTypingIndicator(false);
          }, 1000);
        }
      };

      sendBtn.onclick = () => {
        this.sendMessage(input.value);
        input.value = '';
      };

      // Show welcome message
      const messagesDiv = this.iframeDom.querySelector('.priya-messages');
      const welcomeEl = this.iframeDom.createElement('div');
      welcomeEl.className = 'priya-message priya-message-ai';
      welcomeEl.innerHTML = `<div class="priya-message-content">${this.widgetConfig?.welcome_message || this.config.greeting}</div>`;
      messagesDiv.appendChild(welcomeEl);

      // Show pre-chat form or connect
      this.showPrechatForm();
    }

    // Toggle modal visibility
    toggleModal(bubble, modal) {
      this.isOpen = !this.isOpen;
      modal.style.display = this.isOpen ? 'flex' : 'none';
      if (this.isOpen && !this.isConnected) {
        this.connectWebSocket();
      }
    }

    // Inject styles into page
    injectStyles() {
      const style = document.createElement('style');
      style.textContent = this.getPageStyles();
      document.head.appendChild(style);
    }

    // Get page styles
    getPageStyles() {
      const positionStyles = {
        'bottom-right': { bottom: '20px', right: '20px' },
        'bottom-left': { bottom: '20px', left: '20px' },
        'top-right': { top: '20px', right: '20px' },
        'top-left': { top: '20px', left: '20px' },
      };

      const pos = positionStyles[this.config.position] || positionStyles['bottom-right'];

      return `
        .priya-bubble {
          position: fixed;
          ${Object.entries(pos).map(([k, v]) => `${k}: ${v}`).join('; ')};
          z-index: 9999;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        .priya-bubble-button {
          width: 60px;
          height: 60px;
          border-radius: 50%;
          border: none;
          color: white;
          cursor: pointer;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          transition: all 0.3s ease;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .priya-bubble-button:hover {
          transform: scale(1.1);
          box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
        }

        .priya-bubble-button svg {
          width: 30px;
          height: 30px;
        }

        .priya-badge {
          position: absolute;
          top: -5px;
          right: -5px;
          background: #ef4444;
          color: white;
          border-radius: 50%;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: bold;
        }

        .priya-modal {
          position: fixed;
          ${Object.entries(pos).map(([k, v]) => `${k}: ${v}`).join('; ')};
          width: 400px;
          height: 600px;
          border-radius: 12px;
          box-shadow: 0 5px 40px rgba(0, 0, 0, 0.16);
          z-index: 10000;
          display: none;
          flex-direction: column;
        }

        @media (max-width: 480px) {
          .priya-modal {
            width: 100%;
            height: 100%;
            border-radius: 0;
            ${Object.keys(pos).map(k => `${k}: 0`).join('; ')};
          }
        }

        .priya-iframe {
          width: 100%;
          height: 100%;
          border: none;
          border-radius: 12px;
        }

        .priya-notification {
          position: fixed;
          bottom: 100px;
          right: 20px;
          background: white;
          padding: 16px;
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          z-index: 9998;
          max-width: 300px;
          animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
          from { transform: translateX(400px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }

        .priya-notification-content {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
        }

        .priya-notification-content p {
          margin: 0;
          font-size: 14px;
        }

        .priya-notification-close {
          background: none;
          border: none;
          font-size: 20px;
          cursor: pointer;
          color: #999;
        }
      `;
    }

    // Get iframe styles
    getIframeStyles() {
      return `
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        body {
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: white;
          height: 100%;
          display: flex;
        }

        .priya-container {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          background: white;
          border-radius: 12px;
          overflow: hidden;
        }

        .priya-header {
          padding: 16px;
          color: white;
          flex-shrink: 0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .priya-header h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }

        .priya-close-btn {
          background: none;
          border: none;
          color: white;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .priya-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .priya-message {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .priya-message-ai .priya-message-content {
          background: #f0f0f0;
          color: #333;
          align-self: flex-start;
          max-width: 80%;
        }

        .priya-message-visitor .priya-message-content {
          background: #6366f1;
          color: white;
          align-self: flex-end;
          max-width: 80%;
        }

        .priya-message-content {
          padding: 12px;
          border-radius: 12px;
          font-size: 14px;
          word-wrap: break-word;
        }

        .priya-message-time {
          font-size: 12px;
          color: #999;
          padding: 0 12px;
        }

        .priya-typing-indicator {
          display: flex;
          gap: 4px;
          padding: 12px;
          background: #f0f0f0;
          border-radius: 12px;
          width: fit-content;
        }

        .priya-typing-indicator span {
          width: 8px;
          height: 8px;
          background: #999;
          border-radius: 50%;
          animation: pulse 1.4s infinite;
        }

        .priya-typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .priya-typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }

        .priya-input-area {
          display: flex;
          gap: 8px;
          padding: 12px;
          border-top: 1px solid #eee;
          flex-shrink: 0;
        }

        .priya-input {
          flex: 1;
          border: 1px solid #ddd;
          border-radius: 8px;
          padding: 10px 12px;
          font-size: 14px;
          outline: none;
        }

        .priya-input:focus {
          border-color: #6366f1;
        }

        .priya-send-btn {
          width: 40px;
          height: 40px;
          border: none;
          border-radius: 8px;
          color: white;
          cursor: pointer;
          font-size: 18px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }

        .priya-send-btn:hover {
          transform: scale(1.05);
        }

        .priya-form {
          margin-top: 12px;
        }

        .priya-form-content {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 16px;
          background: #f9f9f9;
          border-radius: 8px;
        }

        .priya-form-content h3 {
          margin: 0;
          font-size: 14px;
          font-weight: 600;
        }

        .priya-form-input {
          padding: 10px;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 14px;
          outline: none;
        }

        .priya-form-input:focus {
          border-color: #6366f1;
        }

        .priya-form-submit,
        .priya-form-skip {
          padding: 10px;
          border: none;
          border-radius: 6px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
        }

        .priya-form-submit {
          background: #6366f1;
          color: white;
        }

        .priya-form-skip {
          background: #e5e7eb;
          color: #333;
        }

        .priya-powered-by {
          text-align: center;
          font-size: 11px;
          color: #999;
          padding: 8px;
          border-top: 1px solid #eee;
        }

        .priya-powered-by a {
          color: #6366f1;
          text-decoration: none;
        }
      `;
    }
  }

  // ========================================================================
  // Initialize Widget on Page Load
  // ========================================================================

  function initWidget() {
    // Get tenant slug from script data attribute
    const script = document.currentScript || document.scripts[document.scripts.length - 1];
    const tenantSlug = script.getAttribute('data-tenant');

    if (!tenantSlug) {
      console.error('[PriyaWidget] Missing data-tenant attribute on script tag');
      return;
    }

    // Parse custom config from data attributes
    const customConfig = {};
    ['color', 'position', 'greeting', 'api-url', 'ws-url'].forEach((attr) => {
      const value = script.getAttribute(`data-${attr}`);
      if (value) {
        const key = attr.replace(/-([a-z])/g, (g) => g[1].toUpperCase());
        customConfig[key] = value;
      }
    });

    // Initialize widget
    window.PriyaWidget = new PriyaWidget(tenantSlug, customConfig);
  }

  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWidget);
  } else {
    initWidget();
  }
})();
