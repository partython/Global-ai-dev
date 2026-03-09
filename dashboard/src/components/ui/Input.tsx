import React from 'react'
import clsx from 'clsx'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  (
    {
      className,
      type = 'text',
      label,
      error,
      helperText,
      leftIcon,
      rightIcon,
      disabled,
      ...props
    },
    ref
  ) => (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
          {label}
          {props.required && <span className="text-danger-600 ml-1">*</span>}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500 dark:text-neutral-400 pointer-events-none">
            {leftIcon}
          </div>
        )}
        <input
          type={type}
          ref={ref}
          disabled={disabled}
          className={clsx(
            'w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 placeholder-neutral-500 dark:placeholder-neutral-400 smooth-transition input-ring disabled:opacity-50 disabled:cursor-not-allowed',
            leftIcon && 'pl-10',
            rightIcon && 'pr-10',
            error && 'border-danger-500 dark:border-danger-400 focus:ring-danger-500',
            className
          )}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 dark:text-neutral-400 pointer-events-none">
            {rightIcon}
          </div>
        )}
      </div>
      {error && <p className="text-xs text-danger-600 dark:text-danger-400 mt-1">{error}</p>}
      {helperText && <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{helperText}</p>}
    </div>
  )
)

Input.displayName = 'Input'

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  helperText?: string
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, helperText, disabled, ...props }, ref) => (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
          {label}
          {props.required && <span className="text-danger-600 ml-1">*</span>}
        </label>
      )}
      <textarea
        ref={ref}
        disabled={disabled}
        className={clsx(
          'w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 placeholder-neutral-500 dark:placeholder-neutral-400 smooth-transition input-ring disabled:opacity-50 disabled:cursor-not-allowed resize-none',
          error && 'border-danger-500 dark:border-danger-400 focus:ring-danger-500',
          className
        )}
        {...props}
      />
      {error && <p className="text-xs text-danger-600 dark:text-danger-400 mt-1">{error}</p>}
      {helperText && <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{helperText}</p>}
    </div>
  )
)

Textarea.displayName = 'Textarea'

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  helperText?: string
  options?: Array<{ value: string; label: string }>
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, error, helperText, options = [], disabled, ...props }, ref) => (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-neutral-900 dark:text-neutral-50 mb-2">
          {label}
          {props.required && <span className="text-danger-600 ml-1">*</span>}
        </label>
      )}
      <select
        ref={ref}
        disabled={disabled}
        className={clsx(
          'w-full px-3 py-2 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 smooth-transition input-ring disabled:opacity-50 disabled:cursor-not-allowed appearance-none',
          error && 'border-danger-500 dark:border-danger-400 focus:ring-danger-500',
          className
        )}
        {...props}
      >
        {props.children}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && <p className="text-xs text-danger-600 dark:text-danger-400 mt-1">{error}</p>}
      {helperText && <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">{helperText}</p>}
    </div>
  )
)

Select.displayName = 'Select'

export default Input
