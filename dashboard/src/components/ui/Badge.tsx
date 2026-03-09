import React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import clsx from 'clsx'

const badgeVariants = cva('badge-base', {
  variants: {
    variant: {
      default: 'bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50',
      primary: 'bg-primary-100 dark:bg-primary-900 text-primary-800 dark:text-primary-200',
      success: 'bg-success-100 dark:bg-success-900 text-success-800 dark:text-success-200',
      warning: 'bg-warning-100 dark:bg-warning-900 text-warning-800 dark:text-warning-200',
      danger: 'bg-danger-100 dark:bg-danger-900 text-danger-800 dark:text-danger-200',
      accent: 'bg-accent-100 dark:bg-accent-900 text-accent-800 dark:text-accent-200',
    },
    size: {
      sm: 'px-2 py-1 text-xs',
      md: 'px-2.5 py-1 text-sm',
      lg: 'px-3 py-1.5 text-base',
    },
  },
  defaultVariants: {
    variant: 'default',
    size: 'md',
  },
})

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode
  onClose?: () => void
}

export const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, size, icon, onClose, children, ...props }, ref) => (
    <div
      ref={ref}
      className={clsx(badgeVariants({ variant, size }), className)}
      {...props}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      <span>{children}</span>
      {onClose && (
        <button
          onClick={onClose}
          className="ml-1 flex-shrink-0 hover:opacity-70 transition-opacity"
          aria-label="Remove badge"
        >
          ×
        </button>
      )}
    </div>
  )
)

Badge.displayName = 'Badge'

export default Badge
