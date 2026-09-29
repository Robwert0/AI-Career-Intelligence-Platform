const PAGES_WITHOUT_BUBBLE = ['/chat', '/match']

export function showsChatBubble(pathname: string): boolean {
  return !PAGES_WITHOUT_BUBBLE.some((page) => pathname === page || pathname.startsWith(`${page}/`))
}
