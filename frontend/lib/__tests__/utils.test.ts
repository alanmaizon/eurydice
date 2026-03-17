import { describe, it, expect } from "vitest"
import { sanitizeText, stripParentheticalTransliterations } from "../utils"

describe("stripParentheticalTransliterations", () => {
  it("strips single-word Latin transliteration after Greek", () => {
    expect(stripParentheticalTransliterations("εἰμί (eimi)")).toBe("εἰμί")
  })

  it("strips capitalized transliteration", () => {
    expect(stripParentheticalTransliterations("Πνεῦμα (Pneuma)")).toBe("Πνεῦμα")
  })

  it("strips polytonic Greek with transliteration", () => {
    expect(stripParentheticalTransliterations("λόγος (logos)")).toBe("λόγος")
  })

  it("strips mid-sentence occurrence", () => {
    expect(
      stripParentheticalTransliterations("The lemma is εἰμί (eimi), the verb to be.")
    ).toBe("The lemma is εἰμί, the verb to be.")
  })

  it("strips multiple occurrences in one string", () => {
    expect(
      stripParentheticalTransliterations("εἰμί (eimi) and λόγος (logos)")
    ).toBe("εἰμί and λόγος")
  })

  it("preserves prose parentheses with no preceding Greek token", () => {
    expect(stripParentheticalTransliterations("Peter (not Paul)")).toBe(
      "Peter (not Paul)"
    )
  })

  it("preserves multi-word parentheticals after Greek", () => {
    expect(stripParentheticalTransliterations("εἰμί (to be)")).toBe("εἰμί (to be)")
  })

  it("preserves parenthetical with numbers", () => {
    expect(stripParentheticalTransliterations("see Homer (Il. 1.1)")).toBe(
      "see Homer (Il. 1.1)"
    )
  })

  it("handles string with no Greek — no change", () => {
    const plain = "The quick brown fox (jumps) over."
    expect(stripParentheticalTransliterations(plain)).toBe(plain)
  })

  it("handles empty string", () => {
    expect(stripParentheticalTransliterations("")).toBe("")
  })
})

describe("sanitizeText", () => {
  it("removes <ctrl46> tokens", () => {
    expect(sanitizeText("<ctrl46>hello")).toBe("hello")
  })

  it("removes arbitrary ctrl tokens", () => {
    expect(sanitizeText("foo<ctrl12>bar")).toBe("foobar")
  })

  it("strips transliteration parens via composition", () => {
    expect(sanitizeText("εἰμί (eimi)")).toBe("εἰμί")
  })

  it("strips ctrl token and transliteration together", () => {
    expect(sanitizeText("<ctrl46>εἰμί (eimi)")).toBe("εἰμί")
  })

  it("preserves normal parentheses after stripping ctrl tokens", () => {
    expect(sanitizeText("Peter (not Paul)")).toBe("Peter (not Paul)")
  })

  it("handles empty string", () => {
    expect(sanitizeText("")).toBe("")
  })
})
