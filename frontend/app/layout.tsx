import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "ΛΟΓΟΣ — Ancient Greek Scholar Console",
  description:
    "A realtime multimodal AI console for Ancient Greek scholarship. Speak, type, or show images to a live philological companion.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="h-full">{children}</body>
    </html>
  )
}
