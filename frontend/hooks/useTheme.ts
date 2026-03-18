"use client"

import { useEffect, useState } from "react"
import { DOMAIN } from "@/lib/constants"

export type Theme = "light" | "dark"

const THEME_KEY = `${DOMAIN}-theme`

export function useTheme() {
  const [theme, setTheme] = useState<Theme>("light")

  useEffect(() => {
    const stored = localStorage.getItem(THEME_KEY) as Theme | null
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
    const initial = stored ?? preferred
    setTheme(initial)
    document.documentElement.classList.toggle("dark", initial === "dark")
  }, [])

  const toggle = () => {
    setTheme((prev) => {
      const next: Theme = prev === "light" ? "dark" : "light"
      document.documentElement.classList.toggle("dark", next === "dark")
      localStorage.setItem(THEME_KEY, next)
      return next
    })
  }

  return { theme, toggle }
}
