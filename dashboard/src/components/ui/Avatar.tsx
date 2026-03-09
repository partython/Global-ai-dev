import React from 'react'
import clsx from 'clsx'

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string
  alt?: string
  name?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}

const sizeClasses = {
  xs: 'h-6 w-6 text-xs',
  sm: 'h-8 w-8 text-sm',
  md: 'h-10 w-10 text-base',
  lg: 'h-12 w-12 text-lg',
  xl: 'h-16 w-16 text-xl',
}

function getInitials(name?: string): string {
  if (!name) return '?'
  const parts = name.split(' ')
  return (parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')
}

const colors = [
  'bg-primary-500',
  'bg-accent-500',
  'bg-success-500',
  'bg-warning-500',
  'bg-danger-500',
]

function getColorByName(name?: string): string {
  if (!name) return colors[0]
  const hash = name.charCodeAt(0) % colors.length
  return colors[hash]
}

export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ className, src, alt, name, size = 'md', ...props }, ref) => {
    const initials = getInitials(name)
    const bgColor = getColorByName(name)

    return (
      <div
        ref={ref}
        className={clsx(
          'rounded-full flex items-center justify-center overflow-hidden flex-shrink-0 font-semibold text-white',
          sizeClasses[size],
          !src && bgColor,
          className
        )}
        {...props}
      >
        {src ? (
          <img src={src} alt={alt || name} className="w-full h-full object-cover" />
        ) : (
          initials
        )}
      </div>
    )
  }
)

Avatar.displayName = 'Avatar'

interface AvatarGroupProps extends React.HTMLAttributes<HTMLDivElement> {
  avatars: Array<{ src?: string; name: string; alt?: string }>
  max?: number
  size?: 'xs' | 'sm' | 'md' | 'lg'
}

export const AvatarGroup = React.forwardRef<HTMLDivElement, AvatarGroupProps>(
  ({ className, avatars, max = 3, size = 'sm', ...props }, ref) => {
    const displayed = avatars.slice(0, max)
    const remaining = avatars.length - max

    return (
      <div
        ref={ref}
        className={clsx('flex items-center -space-x-2', className)}
        {...props}
      >
        {displayed.map((avatar, i) => (
          <Avatar
            key={i}
            src={avatar.src}
            alt={avatar.alt}
            name={avatar.name}
            size={size}
            className="border-2 border-white dark:border-neutral-900"
          />
        ))}
        {remaining > 0 && (
          <Avatar
            name={`+${remaining}`}
            size={size}
            className="border-2 border-white dark:border-neutral-900 bg-neutral-400"
          />
        )}
      </div>
    )
  }
)

AvatarGroup.displayName = 'AvatarGroup'

// shadcn-compatible wrappers
export const AvatarImage: React.FC<{ src?: string; alt?: string }> = ({ src, alt }) => {
  if (!src) return null
  return <img src={src} alt={alt || ''} className="w-full h-full object-cover" />
}

export const AvatarFallback: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return <span className="flex items-center justify-center w-full h-full font-semibold">{children}</span>
}

export default Avatar
