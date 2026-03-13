import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ShortcutRowProps {
  keys: string[]
  description: string
}

interface KeyboardShortcutsOverlayProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// ---------------------------------------------------------------------------
// ShortcutRow
// ---------------------------------------------------------------------------

function ShortcutRow({ keys, description }: ShortcutRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <span className="text-sm text-zinc-300">{description}</span>
      <div className="flex items-center gap-1 shrink-0">
        {keys.map((key, i) => (
          <kbd
            key={i}
            className="inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-mono font-semibold text-zinc-300 bg-zinc-800 border border-zinc-700 rounded min-w-[24px]"
          >
            {key}
          </kbd>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section heading
// ---------------------------------------------------------------------------

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold pt-4 pb-1 first:pt-0">
      {children}
    </h3>
  )
}

// ---------------------------------------------------------------------------
// KeyboardShortcutsOverlay
// ---------------------------------------------------------------------------

export function KeyboardShortcutsOverlay({ open, onOpenChange }: KeyboardShortcutsOverlayProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-zinc-900 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold text-zinc-100">
            Keyboard Shortcuts
          </DialogTitle>
        </DialogHeader>

        <div className="mt-2 divide-y divide-zinc-800">
          {/* Global shortcuts */}
          <div className="pb-3">
            <SectionHeading>Global</SectionHeading>
            <ShortcutRow keys={['Cmd', 'K']} description="Open command palette" />
            <ShortcutRow keys={['?']} description="Show this overlay" />
            <ShortcutRow keys={['Esc']} description="Close dialog / deselect" />
          </div>

          {/* Navigation shortcuts */}
          <div className="py-3">
            <SectionHeading>Navigation (via palette)</SectionHeading>
            <ShortcutRow keys={['G', 'H']} description="Go to Dashboard" />
            <ShortcutRow keys={['G', 'L']} description="Go to Launcher" />
            <ShortcutRow keys={['G', 'R']} description="Go to Runs" />
            <ShortcutRow keys={['G', 'P']} description="Go to Pool Health" />
            <ShortcutRow keys={['G', 'E']} description="Go to Export" />
          </div>

          {/* Trace view shortcuts */}
          <div className="py-3">
            <SectionHeading>Trace View</SectionHeading>
            <ShortcutRow keys={['1']} description="Timeline view" />
            <ShortcutRow keys={['2']} description="Graph view" />
            <ShortcutRow keys={['3']} description="Split view" />
            <ShortcutRow keys={['Esc']} description="Close detail panel" />
          </div>

          {/* Replay shortcuts */}
          <div className="pt-3">
            <SectionHeading>Replay</SectionHeading>
            <ShortcutRow keys={['j']} description="Next step" />
            <ShortcutRow keys={['k']} description="Previous step" />
            <ShortcutRow keys={['ArrowRight']} description="Next step" />
            <ShortcutRow keys={['ArrowLeft']} description="Previous step" />
            <ShortcutRow keys={['Space']} description="Play / Pause" />
            <ShortcutRow keys={['Home']} description="First step" />
            <ShortcutRow keys={['End']} description="Last step" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
