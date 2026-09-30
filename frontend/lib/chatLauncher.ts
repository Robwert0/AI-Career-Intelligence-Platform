// A window event instead of shared state: the bubble lives in the root layout, the entry points
// live in pages, and neither should have to know where the other is mounted.
export const OPEN_CHAT_EVENT = 'chat-bubble:open'

// Marks an inline entry point; the floating launcher steps aside while one is on screen.
export const CHAT_ENTRY_SELECTOR = '[data-chat-entry]'

export function openChatBubble(): void {
  window.dispatchEvent(new Event(OPEN_CHAT_EVENT))
}
