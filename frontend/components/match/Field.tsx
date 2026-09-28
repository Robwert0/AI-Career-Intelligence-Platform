import { ERROR_TEXT } from './styles'

export function FieldError({ id, message }: { id: string; message?: string | null }) {
  if (!message) return null
  return (
    <p id={id} className={ERROR_TEXT}>
      {message}
    </p>
  )
}
