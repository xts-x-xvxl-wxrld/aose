import React from 'react'

export function SkeletonRows({ cols, rows = 5 }) {
  return (
    <>
      {[...Array(rows)].map((_, i) => (
        <tr key={i} className="border-b border-border animate-pulse">
          {[...Array(cols)].map((_, j) => (
            <td key={j} className="px-3 py-2.5">
              <div
                className="h-3.5 bg-muted rounded"
                style={{ width: `${j === 0 ? 60 : 40 + Math.random() * 30}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function SkeletonBlock({ className }) {
  return <div className={`bg-muted rounded animate-pulse ${className || ''}`} />
}
