import { ReactNode } from 'react';

interface AlertProps {
  children: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error';
  className?: string;
}

export function Alert({ children, variant = 'default', className = '' }: AlertProps) {
  const variants = {
    default: 'bg-gray-800 border-gray-700 text-gray-100',
    success: 'bg-green-900/20 border-green-800 text-green-100',
    warning: 'bg-yellow-900/20 border-yellow-800 text-yellow-100',
    error: 'bg-red-900/20 border-red-800 text-red-100',
  };

  return (
    <div className={`rounded-lg border p-4 ${variants[variant]} ${className}`}>
      {children}
    </div>
  );
}

interface AlertDescriptionProps {
  children: ReactNode;
}

export function AlertDescription({ children }: AlertDescriptionProps) {
  return <div className="text-sm">{children}</div>;
}
