// ---------------------------------------------------------------------------
// EventBuffer -- sliding window buffer with eviction tracking
// ---------------------------------------------------------------------------

/**
 * A bounded sliding-window buffer that drops the oldest items when full.
 *
 * Tracks `totalReceived` and `evicted` counts so the UI can display
 * "Showing latest 2,000 of 3,457 events" style indicators.
 */
export class EventBuffer<T> {
  private buffer: T[] = []
  private _totalReceived = 0

  constructor(private readonly maxSize: number = 2000) {}

  /** Add an item, evicting the oldest if the buffer is full. */
  push(item: T): void {
    this._totalReceived++
    this.buffer.push(item)
    if (this.buffer.length > this.maxSize) {
      this.buffer.shift() // drop oldest
    }
  }

  /** Current buffer contents (read-only view). */
  get items(): readonly T[] {
    return this.buffer
  }

  /** Total number of items ever received (including evicted). */
  get totalReceived(): number {
    return this._totalReceived
  }

  /** Number of items that have been evicted from the buffer. */
  get evicted(): number {
    return Math.max(0, this._totalReceived - this.buffer.length)
  }

  /** Current number of items in the buffer. */
  get length(): number {
    return this.buffer.length
  }

  /** Clear all items and reset counters. */
  clear(): void {
    this.buffer = []
    this._totalReceived = 0
  }
}
