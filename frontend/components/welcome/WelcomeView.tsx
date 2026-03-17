"use client"

import { useState } from "react"
import { Mic, Camera, FileText, BookOpen } from "lucide-react"
import type { DifficultyLevel } from "@/lib/types"
import { DIFFICULTY_LABELS, DIFFICULTY_COLORS } from "@/lib/constants"
import { SystemInstructions } from "./SystemInstructions"
import { FeatureCard } from "./FeatureCard"

interface WelcomeViewProps {
  systemInstruction: string
  onSystemInstructionChange: (v: string) => void
  difficultyLevel: DifficultyLevel
  onDifficultyChange: (level: DifficultyLevel) => void
  onLoadPassage: (text: string) => void
}

const LEVELS: DifficultyLevel[] = ["beginner", "intermediate", "advanced"]

export function WelcomeView({
  systemInstruction,
  onSystemInstructionChange,
  difficultyLevel,
  onDifficultyChange,
  onLoadPassage,
}: WelcomeViewProps) {
  const [showPassageInput, setShowPassageInput] = useState(false)
  const [passageText, setPassageText] = useState("")

  const handleLoadPassage = () => {
    if (passageText.trim()) {
      onLoadPassage(passageText.trim())
      setShowPassageInput(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 pt-6 pb-4 overflow-y-auto">
      {/* System instructions */}
      <SystemInstructions
        value={systemInstruction}
        onChange={onSystemInstructionChange}
      />

      {/* Feature E: Difficulty selector */}
      <div>
        <p className="text-xs font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
          Learner level
        </p>
        <div className="flex gap-2">
          {LEVELS.map((level) => {
            const active = level === difficultyLevel
            return (
              <button
                key={level}
                onClick={() => onDifficultyChange(level)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                style={{
                  background: active
                    ? `color-mix(in srgb, ${DIFFICULTY_COLORS[level]} 15%, transparent)`
                    : "var(--surface)",
                  color: active ? DIFFICULTY_COLORS[level] : "var(--text-secondary)",
                  border: `1px solid ${active
                    ? `color-mix(in srgb, ${DIFFICULTY_COLORS[level]} 40%, transparent)`
                    : "var(--border)"}`,
                }}
              >
                {DIFFICULTY_LABELS[level]}
              </button>
            )
          })}
        </div>
      </div>

      {/* Feature D: Passage loader */}
      <div>
        <button
          onClick={() => setShowPassageInput((v) => !v)}
          className="flex items-center gap-2 text-xs font-medium transition-colors"
          style={{ color: showPassageInput ? "var(--accent)" : "var(--text-secondary)" }}
        >
          <BookOpen size={13} />
          {showPassageInput ? "Cancel" : "Load a passage for close reading (optional)"}
        </button>
        {showPassageInput && (
          <div className="mt-2 animate-fade-in">
            <textarea
              value={passageText}
              onChange={(e) => setPassageText(e.target.value)}
              placeholder="Paste Greek text here…"
              rows={4}
              className="w-full rounded-lg px-3 py-2 text-sm greek outline-none resize-y"
              style={{
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text-primary)",
              }}
            />
            <button
              onClick={handleLoadPassage}
              disabled={!passageText.trim()}
              className="mt-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
              style={{
                background: passageText.trim() ? "var(--accent)" : "var(--surface)",
                color: passageText.trim() ? "var(--accent-fg)" : "var(--text-muted)",
                border: passageText.trim() ? "none" : "1px solid var(--border)",
              }}
            >
              Pin passage
            </button>
          </div>
        )}
      </div>

      {/* Feature cards */}
      <div className="flex flex-col sm:flex-row gap-3">
        <FeatureCard
          icon={Mic}
          iconColor="var(--accent)"
          title="Speak to Logos"
          subtitle="Ask questions aloud. Hear correct Attic pronunciation, parsing, and literary analysis — in realtime."
        />
        <FeatureCard
          icon={Camera}
          iconColor="#1a73e8"
          title="Show Logos"
          subtitle="Hold up a manuscript, inscription, or printed page. Logos will read, transcribe, and analyze it."
        />
        <FeatureCard
          icon={FileText}
          iconColor="#0f9d58"
          title="Share your text"
          subtitle="Paste a passage or Greek word. Get morphological parsing, scansion, and close reading on demand."
        />
      </div>

      <p
        className="text-center text-sm pb-2"
        style={{ color: "var(--text-muted)" }}
      >
        Click <strong style={{ color: "var(--text-secondary)" }}>Start session</strong> below to begin streaming
      </p>
    </div>
  )
}
