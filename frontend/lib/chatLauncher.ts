// A window event instead of shared state: the bubble lives in the root layout, the entry points
// live in pages, and neither should have to know where the other is mounted.
export const OPEN_CHAT_EVENT = 'chat-bubble:open'

// Marks an inline entry point; the floating launcher steps aside while one is on screen.
export const CHAT_ENTRY_SELECTOR = '[data-chat-entry]'

// The trigger rides along because Safari and macOS Firefox don't focus a clicked button, so
// document.activeElement can't say where focus should return.
export function openChatBubble(trigger: HTMLElement | null = null): void {
  window.dispatchEvent(new CustomEvent<HTMLElement | null>(OPEN_CHAT_EVENT, { detail: trigger }))
}
