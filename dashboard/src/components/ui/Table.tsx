import React from 'react'
import clsx from 'clsx'

interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {}

export const Table = React.forwardRef<HTMLTableElement, TableProps>(
  ({ className, ...props }, ref) => (
    <div className="overflow-x-auto">
      <table
        ref={ref}
        className={clsx(
          'w-full text-sm text-neutral-900 dark:text-neutral-50',
          className
        )}
        {...props}
      />
    </div>
  )
)

Table.displayName = 'Table'

interface TableHeadProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

export const TableHead = React.forwardRef<HTMLTableSectionElement, TableHeadProps>(
  ({ className, ...props }, ref) => (
    <thead
      ref={ref}
      className={clsx(
        'bg-neutral-50 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-800',
        className
      )}
      {...props}
    />
  )
)

TableHead.displayName = 'TableHead'

interface TableBodyProps extends React.HTMLAttributes<HTMLTableSectionElement> {}

export const TableBody = React.forwardRef<HTMLTableSectionElement, TableBodyProps>(
  ({ className, ...props }, ref) => (
    <tbody
      ref={ref}
      className={clsx(
        'divide-y divide-neutral-200 dark:divide-neutral-800',
        className
      )}
      {...props}
    />
  )
)

TableBody.displayName = 'TableBody'

interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  isClickable?: boolean
}

export const TableRow = React.forwardRef<HTMLTableRowElement, TableRowProps>(
  ({ className, isClickable, ...props }, ref) => (
    <tr
      ref={ref}
      className={clsx(
        'smooth-transition',
        isClickable && 'hover:bg-neutral-50 dark:hover:bg-neutral-800 cursor-pointer',
        className
      )}
      {...props}
    />
  )
)

TableRow.displayName = 'TableRow'

interface TableHeaderCellProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  align?: 'left' | 'center' | 'right'
}

export const TableHeaderCell = React.forwardRef<HTMLTableCellElement, TableHeaderCellProps>(
  ({ className, align = 'left', ...props }, ref) => (
    <th
      ref={ref}
      className={clsx(
        'px-6 py-3 text-left font-semibold text-neutral-700 dark:text-neutral-300',
        align === 'center' && 'text-center',
        align === 'right' && 'text-right',
        className
      )}
      {...props}
    />
  )
)

TableHeaderCell.displayName = 'TableHeaderCell'

interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  align?: 'left' | 'center' | 'right'
}

export const TableCell = React.forwardRef<HTMLTableCellElement, TableCellProps>(
  ({ className, align = 'left', ...props }, ref) => (
    <td
      ref={ref}
      className={clsx(
        'px-6 py-4',
        align === 'center' && 'text-center',
        align === 'right' && 'text-right',
        className
      )}
      {...props}
    />
  )
)

TableCell.displayName = 'TableCell'

export default Table
