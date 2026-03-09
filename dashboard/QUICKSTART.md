# Quick Start Guide - Priya Global Dashboard

## Installation & Setup (5 minutes)

### Step 1: Install Dependencies
```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard
npm install
```

### Step 2: Configure Environment
```bash
cp .env.example .env.local
```

Edit `.env.local` if needed (defaults work for local development):
```
NEXT_PUBLIC_API_URL=http://localhost:9000
NEXTAUTH_URL=http://localhost:3000
```

### Step 3: Run Development Server
```bash
npm run dev
```

The application will be available at **http://localhost:3000**

## What's Included

### Public Pages (No Login Required)
- **Homepage** (`/`) - Beautiful SaaS landing page
- **Login** (`/login`) - Email/password + OAuth login
- **Register** (`/register`) - Signup with business details

### Dashboard Pages (Login Required)
- **Dashboard** (`/dashboard`) - Main dashboard with stats and charts
- **Conversations** (`/conversations`) - Chat inbox with split view
- **Customers** (`/customers`) - CRM with customer profiles
- **Channels** (`/channels`) - WhatsApp, Email, Voice, Instagram, Facebook, Web
- **Knowledge Base** (`/knowledge-base`) - AI training documents
- **Funnels** (`/funnels`) - Sales funnel builder
- **Handoffs** (`/handoffs`) - Agent takeover management
- **CSAT** (`/csat`) - Customer satisfaction tracking
- **Settings** (`/settings`) - 6 configuration sections

## File Structure

```
/src
  /app                    # Next.js pages
    page.tsx             # Landing page
    layout.tsx           # Root layout
    (auth)/              # Auth routes
      login/
      register/
    (dashboard)/         # Protected dashboard
      layout.tsx         # Dashboard wrapper
      dashboard/
      conversations/
      customers/
      channels/
      settings/
      [+ 4 more pages]

  /components
    /ui                  # Reusable UI components
      Button, Card, Input, Badge, Avatar, Modal, Table, Tabs
    /layout              # Layout components
      Sidebar, Header

  /lib
    api.ts              # API client wrapper
    auth.ts             # Auth utilities

  /stores
    auth.ts             # Zustand auth store

  /types
    index.ts            # TypeScript definitions

  /styles
    globals.css         # Global styles

Configuration Files:
  - package.json         # Dependencies
  - tsconfig.json        # TypeScript config
  - tailwind.config.ts   # Tailwind themes
  - next.config.js       # Next.js config
  - postcss.config.js    # PostCSS config
```

## Technology Stack

| Technology | Purpose | Notes |
|-----------|---------|-------|
| **Next.js 14** | Framework | App Router, Server Components |
| **TypeScript** | Language | Strict mode, full type safety |
| **Tailwind CSS** | Styling | Custom color palette, dark mode |
| **Zustand** | State Management | Auth store with persistence |
| **Framer Motion** | Animations | Page transitions & effects |
| **Recharts** | Charts | Revenue, funnel, CSAT visualizations |
| **Lucide React** | Icons | 300+ icons included |
| **next-auth** | Auth | Session management ready |

## UI Components

All components are pre-built and ready to use:

```tsx
// Button variants
<Button variant="primary" size="lg">Click me</Button>
<Button variant="secondary" isLoading={true}>Saving...</Button>

// Form inputs
<Input label="Email" type="email" placeholder="you@example.com" />
<Input label="Password" type="password" leftIcon={<Lock />} />
<Select label="Role" options={roles} />
<Textarea label="Message" rows={5} />

// Display components
<Badge variant="primary">Active</Badge>
<Avatar name="John Doe" size="md" />
<Card>
  <CardHeader><CardTitle>Title</CardTitle></CardHeader>
  <CardContent>Content</CardContent>
</Card>

// Layout
<Table>
  <TableHead>
    <TableRow>
      <TableHeaderCell>Name</TableHeaderCell>
    </TableRow>
  </TableHead>
  <TableBody>
    <TableRow>
      <TableCell>John</TableCell>
    </TableRow>
  </TableBody>
</Table>

// Modals & Dialogs
<Modal isOpen={isOpen} onClose={close} title="Delete?">
  Are you sure?
</Modal>

// Tabs
<Tabs defaultValue="tab1">
  <TabsList>
    <TabsTrigger value="tab1">Tab 1</TabsTrigger>
  </TabsList>
  <TabsContent value="tab1">Content</TabsContent>
</Tabs>
```

## Authentication Flow

### Login
```tsx
import { useAuthActions } from '@/lib/auth'

function LoginPage() {
  const { handleLogin } = useAuthActions()

  const onSubmit = async (email, password) => {
    await handleLogin(email, password)
    // Auto-redirects to /dashboard
  }
}
```

### Protect Routes
```tsx
'use client'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/stores/auth'

export default function DashboardLayout({ children }) {
  const router = useRouter()
  const isAuthenticated = useAuth((state) => state.isAuthenticated)

  useEffect(() => {
    if (!isAuthenticated) router.push('/login')
  }, [isAuthenticated])

  return isAuthenticated ? children : null
}
```

### Access User Info
```tsx
import { useAuth } from '@/stores/auth'

function Component() {
  const user = useAuth((state) => state.user)
  const tenant = useAuth((state) => state.tenant)
  const logout = useAuth((state) => state.logout)

  return <div>Welcome {user?.name}</div>
}
```

## API Integration

### Making API Calls
```tsx
import { api, customerAPI, conversationAPI } from '@/lib/api'

// Direct API call
const data = await api.get('/endpoint')

// Pre-built API methods
const customers = await customerAPI.list()
const customer = await customerAPI.get('id')
const conversations = await conversationAPI.list()

// With error handling
try {
  const result = await api.post('/endpoint', { data })
} catch (error) {
  console.error(error.message)
}
```

### API Base URL
Default: `http://localhost:9000`

Change via environment variable:
```bash
NEXT_PUBLIC_API_URL=https://api.example.com
```

## Styling & Theming

### Colors
```tsx
// Use Tailwind classes
<div className="bg-primary-600 text-white">Primary</div>
<div className="bg-accent-600 text-white">Accent</div>
<div className="bg-success-600">Success</div>
<div className="bg-warning-600">Warning</div>
<div className="bg-danger-600">Danger</div>
```

### Dark Mode
Dark mode is automatic with `dark:` classes:
```tsx
<div className="bg-white dark:bg-neutral-900 text-black dark:text-white">
  Works in both modes
</div>
```

### Responsive Design
```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  1 column on mobile, 2 on tablet, 4 on desktop
</div>
```

## Common Patterns

### Data Fetching
```tsx
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export default function Page() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/endpoint')
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div>Loading...</div>
  return <div>{/* render data */}</div>
}
```

### Form Handling
```tsx
'use client'
import { useState } from 'react'
import { Input, Button } from '@/components/ui'

export default function Form() {
  const [formData, setFormData] = useState({ email: '', password: '' })
  const [errors, setErrors] = useState({})
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsLoading(true)

    try {
      // submit form
    } catch (error) {
      setErrors({ submit: error.message })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Input
        label="Email"
        value={formData.email}
        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
        error={errors.email}
      />
      <Button isLoading={isLoading}>Submit</Button>
    </form>
  )
}
```

### Charts
```tsx
import { LineChart, Line, ResponsiveContainer } from 'recharts'

const data = [
  { month: 'Jan', value: 100 },
  { month: 'Feb', value: 120 },
]

export default function Chart() {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data}>
        <Line dataKey="value" stroke="#2563eb" />
      </LineChart>
    </ResponsiveContainer>
  )
}
```

## Build & Deploy

### Development Build
```bash
npm run build
npm run start
```

### Production Build
```bash
# Build
npm run build

# Deploy to Vercel
npx vercel

# Or deploy to your own server
docker build -t priya-dashboard .
docker run -p 3000:3000 priya-dashboard
```

## Common Issues

### Port Already in Use
```bash
# Use a different port
npm run dev -- -p 3001
```

### Module Not Found
```bash
# Clear cache and reinstall
rm -rf node_modules .next
npm install
```

### Authentication Not Working
1. Check `NEXT_PUBLIC_API_URL` environment variable
2. Ensure backend is running on correct port
3. Verify API endpoints match expected format

### Tailwind Styles Not Applied
1. Ensure file is in `src/` directory
2. Check tailwind.config.ts includes correct paths
3. Restart dev server: `npm run dev`

## Next Steps

1. **Connect Backend API**
   - Update `NEXT_PUBLIC_API_URL` in `.env.local`
   - Test endpoints with Postman/Insomnia

2. **Customize Branding**
   - Update logo in Sidebar
   - Modify colors in tailwind.config.ts
   - Update company name throughout

3. **Add Features**
   - Create new pages in `/app/(dashboard)/`
   - Add API methods in `/lib/api.ts`
   - Use existing components

4. **Deploy**
   - Push to GitHub
   - Connect to Vercel
   - Configure environment variables

## Resources

- **Next.js Docs**: https://nextjs.org/docs
- **Tailwind CSS**: https://tailwindcss.com
- **React Docs**: https://react.dev
- **TypeScript**: https://www.typescriptlang.org
- **Zustand**: https://github.com/pmndrs/zustand
- **Framer Motion**: https://www.framer.com/motion
- **Recharts**: https://recharts.org

## Support

For issues or questions, refer to the PROJECT_STRUCTURE.md file for detailed documentation.
