import type { LucideIcon } from "lucide-react"

interface FeatureCardProps {
  icon: LucideIcon
  iconColor?: string
  title: string
  subtitle: string
}

export function FeatureCard({ icon: Icon, iconColor = "var(--accent)", title, subtitle }: FeatureCardProps) {
  return (
    <div
      className="flex-1 min-w-[200px] rounded-xl p-5 transition-colors hover:bg-[var(--surface-hover)] cursor-default"
      style={{
        border: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div className="flex items-start gap-3">
        <span
          className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5"
          style={{ background: `color-mix(in srgb, ${iconColor} 15%, transparent)` }}
        >
          <Icon size={16} style={{ color: iconColor }} />
        </span>
        <div>
          <p className="text-sm font-medium mb-1" style={{ color: "var(--text-primary)" }}>
            {title}
          </p>
          <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            {subtitle}
          </p>
        </div>
      </div>
    </div>
  )
}
