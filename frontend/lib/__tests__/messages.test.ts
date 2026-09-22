import { describe, expect, it } from 'vitest'
import { authErrorMessage } from '../messages'

function failure(status: number, detail = 'server detail', retryAfter?: number) {
  return { ok: false as const, status, detail, retryAfter }
}

describe('authErrorMessage', () => {
  it('explains a conflict as an existing account', () => {
    expect(authErrorMessage(failure(409))).toBe('That email is already registered.')
  })

  it('stays ambiguous about which credential was wrong', () => {
    const message = authErrorMessage(failure(401, 'Invalid email or password'))

    expect(message).toBe('Email or password is incorrect.')
    expect(message.toLowerCase()).toContain('email')
    expect(message.toLowerCase()).toContain('password')
  })

  it('never reveals whether an account exists', () => {
    const message = authErrorMessage(failure(401, 'Invalid email or password'))

    expect(message).not.toMatch(/no account|not found|does not exist|unknown email|unregistered/i)
  })

  it('answers identically for a 403', () => {
    expect(authErrorMessage(failure(403))).toBe(authErrorMessage(failure(401)))
  })

  it('surfaces the server detail for a validation error', () => {
    expect(authErrorMessage(failure(422, 'String should have at least 8 characters'))).toBe(
      'String should have at least 8 characters',
    )
  })

  it('includes the wait time when the server sends one', () => {
    expect(authErrorMessage(failure(429, 'Too many requests', 45))).toBe(
      'Too many attempts. Try again in 45 seconds.',
    )
  })

  it('handles a rate limit with no retry hint', () => {
    expect(authErrorMessage(failure(429, 'Too many requests'))).toBe(
      'Too many attempts. Try again shortly.',
    )
  })

  it('uses the singular for a one second wait', () => {
    expect(authErrorMessage(failure(429, 'Too many requests', 1))).toBe(
      'Too many attempts. Try again in 1 second.',
    )
  })

  it('renders a long register cooldown in minutes, not seconds', () => {
    expect(authErrorMessage(failure(429, 'Too many requests', 1200))).toBe(
      'Too many attempts. Try again in 20 minutes.',
    )
  })

  it('reports a network failure plainly', () => {
    expect(authErrorMessage(failure(0, 'Could not reach the server'))).toBe(
      'Could not reach the server.',
    )
  })

  it('does not leak a raw server detail for a 500', () => {
    const message = authErrorMessage(failure(500, 'Traceback: secret internal detail'))

    expect(message).toBe('Something went wrong. Please try again.')
    expect(message).not.toContain('Traceback')
  })

  it('treats a 503 as temporary', () => {
    expect(authErrorMessage(failure(503))).toBe('The service is busy. Please try again shortly.')
  })
})
