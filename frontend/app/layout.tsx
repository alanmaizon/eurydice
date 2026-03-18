import type { Metadata } from "next"
import "./globals.css"

const isEurydice = process.env.NEXT_PUBLIC_DOMAIN === "eurydice"

export const metadata: Metadata = {
  title: isEurydice
    ? "ΕΥΡΥΔΙΚΗ — AI Guitar Coach"
    : "ΛΟΓΟΣ — Ancient Greek Scholar Console",
  description: isEurydice
    ? "A realtime AI guitar coaching console. Record, analyze, and master short passages with structured feedback."
    : "A realtime multimodal AI console for Ancient Greek scholarship. Speak, type, or show images to a live philological companion.",
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
