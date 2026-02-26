'use client';

import { useState, useRef } from 'react';

interface SliderProps {
  value: number[];
  onValueChange: (value: number[]) => void;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
}

export function Slider({ value, onValueChange, min, max, step, disabled = false }: SliderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const sliderRef = useRef<HTMLDivElement>(null);

  const currentValue = value[0] || min;
  const percentage = ((currentValue - min) / (max - min)) * 100;

  const updateValue = (clientX: number) => {
    if (!sliderRef.current || disabled) return;

    const rect = sliderRef.current.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const rawValue = min + percent * (max - min);
    const steppedValue = Math.round(rawValue / step) * step;
    const clampedValue = Math.max(min, Math.min(max, steppedValue));

    onValueChange([clampedValue]);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    updateValue(e.clientX);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (isDragging) {
      updateValue(e.clientX);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Add/remove global mouse event listeners
  if (typeof window !== 'undefined') {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }

  return (
    <div
      ref={sliderRef}
      onMouseDown={handleMouseDown}
      className={`relative flex h-5 w-full touch-none items-center ${
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
      }`}
    >
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-gray-700">
        <div
          className="absolute h-full bg-primary-600 transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div
        className="absolute h-5 w-5 rounded-full border-2 border-primary-600 bg-white shadow-lg transition-transform hover:scale-110"
        style={{ left: `calc(${percentage}% - 10px)` }}
      />
    </div>
  );
}
