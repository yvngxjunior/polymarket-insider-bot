import './globals.css'

export const metadata = {
  title: 'PolyInsider Cockpit',
  description: 'Trading dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-white antialiased">{children}</body>
    </html>
  )
}
