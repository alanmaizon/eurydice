interface ImageMessageProps {
  src: string
  alt?: string
}

export function ImageMessage({ src, alt = "Sent image" }: ImageMessageProps) {
  return (
    <div className="mt-2 animate-fade-in">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="rounded-lg max-w-[280px] max-h-[200px] object-cover"
        style={{ border: "1px solid var(--border)" }}
      />
    </div>
  )
}
