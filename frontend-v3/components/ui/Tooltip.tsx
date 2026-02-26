'use client'
import { useState } from 'react'

export function Tooltip({ text, children }: { text: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative inline-block">
      <span onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
        {children}
      </span>
      {show && (
        <div className="absolute z-50 bg-gray-800 text-white text-xs p-2 rounded shadow-lg -top-10 left-0 w-64 border border-gray-700">
          {text}
        </div>
      )}
    </div>
  )
}
