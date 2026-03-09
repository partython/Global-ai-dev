# Priya Global Dashboard - Project Structure

## Overview
This is a production-ready Next.js 14 unified website + dashboard for Priya Global. The same application serves as both the public marketing website and the post-login dashboard.

## Project Setup

### Installation
```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard
npm install
```

### Development
```bash
npm run dev
```
The app will be available at `http://localhost:3000`

### Build & Deploy
```bash
npm run build
npm run start
```

## Architecture

### Technology Stack
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS + Custom Components
- **State Management**: Zustand
- **UI Components**: Custom shadcn-style components
- **Animations**: Framer Motion
- **Charts**: Recharts
- **Icons**: Lucide React
- **Authentication**: next-auth with custom implementation
- **HTTP Client**: Native Fetch API with custom wrapper

### Directory Structure

```
src/
├── app/                          # Next.js App Router
│   ├── layout.tsx               # Root layout with metadata
│   ├── page.tsx                 # Landing/marketing page
│   ├── (auth)/                  # Auth group
│   │   ├── login/page.tsx       # Login page
│   │   └── register/page.tsx    # Registration page
│   └── (dashboard)/             # Dashboard group
│       ├── layout.tsx           # Dashboard layout with sidebar
│       ├── dashboard/page.tsx   # Main dashboard/home
│       ├── conversations/page.tsx
│       ├── customers/page.tsx
│       ├── channels/page.tsx
│       ├── knowledge-base/page.tsx
│       ├── funnels/page.tsx
│       ├── handoffs/page.tsx
│       ├── csat/page.tsx
│       └── settings/page.tsx
│
├── components/
│   ├── ui/                       # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Input.tsx
│   │   ├── Badge.tsx
│   │   ├── Avatar.tsx
│   │   ├── Modal.tsx
│   │   ├── Table.tsx
│   │   └── Tabs.tsx
│   ├── layout/                   # Layout components
│   │   ├── Sidebar.tsx          # Collapsible dashboard sidebar
│   │   └── Header.tsx           # Top navigation with dark mode
│   └── dashboard/               # Dashboard-specific components
│
├── lib/
│   ├── api.ts                   # API client wrapper with auth
│   └── auth.ts                  # Authentication utilities
│
├── stores/
│   └── auth.ts                  # Zustand auth store
│
├── types/
│   └── index.ts                 # TypeScript type definitions
│
└── styles/
    └── globals.css              # Global styles with Tailwind directives
```

## Key Features

### 1. Public Pages
- **Landing Page** (`/`)
  - Hero section with animated gradient text
  - Features grid (6 channels)
  - How it works section (3 steps)
  - Pricing section (3 tiers)
  - Testimonials carousel
  - CTA sections
  - Professional footer

- **Login Page** (`/login`)
  - Email/password authentication
  - OAuth options (Google, Microsoft, Apple)
  - Password recovery link
  - Link to registration

- **Register Page** (`/register`)
  - Form validation
  - Business name, full name, email, password
  - OAuth signup options
  - Terms & conditions checkbox
  - Redirects to AI training after signup

### 2. Protected Dashboard Pages
All protected pages require authentication via `/login`

#### Dashboard (`/dashboard`)
- Welcome banner with tenant name
- 4 stats cards: Conversations, Revenue, Response Time, CSAT
- Recent conversations list (split view)
- Channel distribution pie chart
- Funnel overview with conversion rates
- Quick action buttons
- Revenue trend chart (6 months)

#### Conversations (`/conversations`)
- 3-column layout: List | Chat | Metadata
- Real-time conversation filtering
- Message history with timestamps
- Agent takeover mode
- Unread indicators
- Channel badges
- Customer information sidebar

#### Customers (`/customers`)
- Search and filter customers
- Sortable table with 6 columns
- Customer detail sidebar
- Lead score visualization
- Order history and spending
- Contact information
- Quick action buttons

#### Channels (`/channels`)
- Channel card grid (6 channels)
- Status indicators (connected/disconnected)
- Message count and last active
- Channel settings modal
- Auto-response configuration
- Connect/disconnect buttons
- Performance distribution chart

#### Knowledge Base (`/knowledge-base`)
- Document management
- Add/edit/delete documents
- Training interface for AI
- FAQ management
- Product information repository

#### Funnels (`/funnels`)
- Sales funnel builder
- Multi-stage funnels
- Conversion tracking
- Automation rules

#### Handoffs (`/handoffs`)
- Agent takeover requests
- Status tracking (pending, accepted)
- Conversation details
- Agent assignment

#### CSAT (`/csat`)
- Customer satisfaction scores
- Rating distribution
- Trend analysis (6 months)
- Feedback responses
- Star rating visualization

#### Settings (`/settings`)
- **General**: Business info, timezone, language
- **AI Config**: AI name, personality, system prompt, max discount
- **Team**: Member management, invitations, roles
- **Billing**: Plan info, usage metrics, upgrade option
- **Security**: 2FA, active sessions, logout options
- **API Keys**: Create, revoke, manage API keys

### 3. UI Components Library
All components are custom-built with Tailwind CSS:

#### Button
- Variants: primary, secondary, ghost, danger, success, outline
- Sizes: xs, sm, md, lg, xl, icon
- States: loading, disabled
- Icons: left/right icons
- Full width option

#### Card
- CardHeader, CardContent, CardFooter
- CardTitle, CardDescription
- Elevation and hover effects

#### Input System
- Input (text, email, password, etc.)
- Textarea (multi-line)
- Select (dropdown)
- Label, error, helper text
- Icons (left/right)

#### Badge
- Variants: default, primary, success, warning, danger, accent
- Sizes: sm, md, lg
- Closeable with optional onClose
- Icon support

#### Avatar
- Fallback to initials from name
- Configurable sizes
- AvatarGroup for multiple avatars with "+N more"

#### Modal
- Backdrop click handling
- Escape key close
- Size options
- Custom header/footer

#### Table
- Table, TableHead, TableBody
- TableRow (with hover support)
- TableHeaderCell, TableCell
- Alignment options

#### Tabs
- Controlled tabs with TabsContext
- TabsList, TabsTrigger, TabsContent
- Smooth transitions

### 4. Authentication System

#### Login Flow
1. User enters email/password
2. API call to `/auth/login`
3. Server returns token + user + tenant
4. Zustand store updates
5. Redirect to `/dashboard`

#### OAuth Flow
1. User clicks OAuth button
2. OAuth provider redirects
3. Token exchanged at backend
4. Same as login flow

#### Protected Routes
- Dashboard layout checks `useAuth()` hook
- Redirects to `/login` if unauthenticated
- Token persisted in localStorage (via Zustand middleware)

### 5. API Integration

#### Base URL
Default: `http://localhost:9000`
Configurable via `NEXT_PUBLIC_API_URL` env var

#### API Endpoints (Mock-ready)

**Authentication**
- `POST /auth/login` - Email/password login
- `POST /auth/register` - New account creation
- `POST /auth/google` - Google OAuth
- `POST /auth/logout` - Logout
- `POST /auth/refresh` - Token refresh

**Conversations**
- `GET /conversations` - List conversations
- `GET /conversations/:id` - Get conversation detail
- `GET /conversations/search?q=` - Search
- `PATCH /conversations/:id/read` - Mark as read
- `PATCH /conversations/:id/assign` - Assign agent
- `PATCH /conversations/:id/close` - Close
- `POST /conversations/:id/messages` - Add message

**Customers**
- `GET /customers` - List customers
- `GET /customers/:id` - Get customer detail
- `GET /customers/search?q=` - Search
- `PATCH /customers/:id` - Update profile
- `GET /customers/:id/orders` - Customer orders
- `GET /customers/:id/tags` - Customer tags
- `POST /customers/:id/tags` - Add tag

**Channels**
- `GET /channels` - List all channels
- `GET /channels/:id` - Get channel detail
- `POST /channels` - Connect channel
- `PATCH /channels/:id` - Update settings
- `DELETE /channels/:id` - Disconnect
- `GET /channels/:id/stats` - Channel statistics

**Dashboard**
- `GET /dashboard/stats` - Dashboard stats
- `GET /dashboard/conversations?limit=5` - Recent conversations
- `GET /dashboard/channels/distribution` - Channel breakdown
- `GET /dashboard/funnel` - Funnel data
- `GET /dashboard/activity` - Recent activity

**Settings**
- `GET /settings/general` - General settings
- `PATCH /settings/general` - Update general
- `GET /settings/ai` - AI settings
- `PATCH /settings/ai` - Update AI config
- `GET /settings/team` - Team members
- `POST /settings/team/invite` - Invite member
- `DELETE /settings/team/:id` - Remove member
- `GET /settings/billing` - Billing info
- `GET /settings/api-keys` - API keys
- `POST /settings/api-keys` - Create API key
- `DELETE /settings/api-keys/:id` - Revoke API key

#### Error Handling
- 401 Unauthorized → Redirect to `/login`
- 4xx/5xx → Throw error with message
- Network errors → Display user-friendly message

### 6. Styling System

#### Colors
- **Primary**: Blue-600 (`#2563eb`)
- **Accent**: Purple-600 (`#9333ea`)
- **Success**: Green-600 (`#16a34a`)
- **Warning**: Amber-600 (`#d97706`)
- **Danger**: Red-600 (`#dc2626`)
- **Neutral**: Gray scale (50-950)

#### Dark Mode
- Automatic with `dark:` classes
- Toggle in header
- Persists in localStorage (can be added)

#### Responsive Design
- Mobile-first approach
- Breakpoints: sm (640px), md (768px), lg (1024px), xl (1280px), 2xl (1536px)
- Sidebar → Bottom nav on mobile
- Responsive grids and tables

#### Animations
- Framer Motion for page transitions
- Smooth transitions on components
- Hover effects and interactive states
- Loading spinners and skeletons (ready to implement)

### 7. Type Safety
Complete TypeScript coverage with types for:
- User & Tenant
- Channels & Conversations
- Customers & Orders
- Messages & Conversations
- API Responses
- Form Payloads

## Configuration Files

### package.json
- All dependencies pre-configured
- Scripts: dev, build, start

### tsconfig.json
- Strict mode enabled
- Path aliases (@/*, @/components/*, etc.)
- React JSX transform
- Module resolution: bundler

### tailwind.config.ts
- Custom color palette
- Extended animations (fade-in, slide-in, gradient-shift)
- Form and typography plugins ready

### next.config.js
- Image optimization
- CORS headers configured
- SWC minification

## Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Set Environment Variables
```bash
cp .env.example .env.local
# Edit .env.local with your configuration
```

### 3. Run Development Server
```bash
npm run dev
```

### 4. Access the Application
- Marketing Site: http://localhost:3000
- Login: http://localhost:3000/login
- Register: http://localhost:3000/register
- Dashboard: http://localhost:3000/dashboard (after login)

## Testing

### Login Credentials (Mock)
Email: demo@example.com
Password: password123

### API Base URL
Update `NEXT_PUBLIC_API_URL` to point to your backend API

## Deployment

### Vercel (Recommended)
```bash
npm install -g vercel
vercel
```

### Docker
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

### Environment Variables for Production
- `NEXT_PUBLIC_API_URL`: Your production API URL
- `NEXTAUTH_URL`: Your production domain
- `NEXTAUTH_SECRET`: Secure random string

## Performance Optimizations

- Server-side rendering where beneficial
- Image optimization with next/image
- Code splitting by route
- Lazy loading of components
- Optimized bundle size
- CSS-in-JS via Tailwind (zero runtime)

## Security Features

- CSRF protection via next-auth
- XSS prevention with React escaping
- Secure authentication with HTTP-only cookies
- Input validation on forms
- Protected API endpoints

## Future Enhancements

1. Real-time updates with WebSocket/Socket.io
2. Notification system
3. Advanced analytics
4. Custom reports
5. Bulk operations
6. Export functionality
7. Audit logs
8. Advanced search filters
9. Mobile app support
10. Integration marketplace

## Support & Documentation

For issues or questions, refer to:
- Next.js Docs: https://nextjs.org
- Tailwind Docs: https://tailwindcss.com
- React Docs: https://react.dev
- TypeScript Docs: https://www.typescriptlang.org
