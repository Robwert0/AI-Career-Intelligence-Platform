// Pydantic counts code points; String.length counts UTF-16 units, so an emoji would count twice.
export function charCount(value: string): number {
  return Array.from(value).length
}
