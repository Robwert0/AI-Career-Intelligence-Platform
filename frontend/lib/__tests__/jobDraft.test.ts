import { describe, expect, it } from 'vitest'
import {
  addItem,
  draftErrors,
  hasDraftErrors,
  MAX_ITEMS,
  moveItem,
  removeItem,
  toDraft,
  toPosting,
  updateItem,
  type JobDraft,
} from '../jobDraft'
import type { JobPosting } from '../match'

const POSTING: JobPosting = {
  title: 'Backend Engineer',
  company: 'Acme',
  responsibilities: ['Build APIs'],
  required: [
    { text: '5 years of Go', sensitive: false },
    { text: 'Right to work in the UK', sensitive: true },
  ],
  preferred: [{ text: 'Kubernetes', sensitive: false }],
}

function keys() {
  let n = 0
  return () => `k${++n}`
}

function draft(posting: JobPosting = POSTING): JobDraft {
  return toDraft(posting, keys())
}

function manyItems(size: number) {
  return Array.from({ length: size }, (_, index) => ({ text: `item ${index}`, sensitive: false }))
}

describe('toDraft and toPosting', () => {
  it('round-trips a posting unchanged', () => {
    expect(toPosting(draft())).toEqual(POSTING)
  })

  it('keys every item in order and keeps the sensitive flag', () => {
    const d = draft()

    expect(d.responsibilities.map((item) => item.key)).toEqual(['k1'])
    expect(d.required.map((item) => [item.key, item.sensitive])).toEqual([
      ['k2', false],
      ['k3', true],
    ])
  })

  it('shows a missing company as an empty field and sends it back as null', () => {
    const d = draft({ ...POSTING, company: null })

    expect(d.company).toBe('')
    expect(toPosting(d).company).toBeNull()
  })

  it('trims text and drops items left blank', () => {
    const edited = updateItem(
      updateItem(draft(), 'required', 'k2', '  6 years of Go  '),
      'preferred',
      'k4',
      '   ',
    )

    expect(toPosting(edited).required[0].text).toBe('6 years of Go')
    expect(toPosting(edited).preferred).toEqual([])
  })
})

describe('editing', () => {
  it('adds an empty, non-sensitive item under the given key', () => {
    expect(addItem(draft(), 'preferred', 'new').preferred.at(-1)).toEqual({
      key: 'new',
      text: '',
      sensitive: false,
    })
  })

  it('does not add past the limit', () => {
    const full = draft({ ...POSTING, preferred: manyItems(MAX_ITEMS) })

    expect(addItem(full, 'preferred', 'new')).toBe(full)
  })

  it('updates only the matching item', () => {
    const d = updateItem(draft(), 'required', 'k3', 'Visa sponsorship available')

    expect(d.required.map((item) => item.text)).toEqual([
      '5 years of Go',
      'Visa sponsorship available',
    ])
  })

  it('resets the sensitive flag once the text is edited: the server, not the client, re-checks it on submit', () => {
    const d = updateItem(draft(), 'required', 'k3', 'Visa sponsorship available')

    expect(d.required[1].sensitive).toBe(false)
  })

  it('still resets sensitive to false even when the edit leaves the text unchanged', () => {
    const d = updateItem(draft(), 'required', 'k3', 'Right to work in the UK')

    expect(d.required[1].sensitive).toBe(false)
  })

  it('removes an item', () => {
    expect(removeItem(draft(), 'required', 'k2').required.map((item) => item.key)).toEqual(['k3'])
  })

  it('moves a requirement to the end of the other list, keeping text and flag', () => {
    const d = moveItem(draft(), 'required', 'k3')

    expect(d.required.map((item) => item.key)).toEqual(['k2'])
    expect(d.preferred.at(-1)).toEqual({
      key: 'k3',
      text: 'Right to work in the UK',
      sensitive: true,
    })
  })

  it('does not move into a full list', () => {
    const full = draft({ ...POSTING, preferred: manyItems(MAX_ITEMS) })

    expect(moveItem(full, 'required', 'k2')).toBe(full)
  })

  it('ignores an unknown key', () => {
    const d = draft()

    expect(moveItem(d, 'required', 'nope')).toBe(d)
  })
})

describe('draftErrors', () => {
  it('accepts the extracted posting', () => {
    expect(hasDraftErrors(draftErrors(draft()))).toBe(false)
  })

  it('requires a title', () => {
    expect(draftErrors({ ...draft(), title: '   ' }).title).toBeDefined()
  })

  it('limits the title to 200 characters', () => {
    expect(draftErrors({ ...draft(), title: 'x'.repeat(200) }).title).toBeUndefined()
    expect(draftErrors({ ...draft(), title: 'x'.repeat(201) }).title).toBeDefined()
  })

  it('limits the company to 200 characters', () => {
    expect(draftErrors({ ...draft(), company: 'x'.repeat(201) }).company).toBeDefined()
  })

  it('flags an item over 300 characters by its key', () => {
    const d = updateItem(draft(), 'required', 'k2', 'x'.repeat(301))

    expect(Object.keys(draftErrors(d).items)).toEqual(['k2'])
  })

  it('counts characters the way the backend does', () => {
    const d = updateItem(draft(), 'required', 'k2', '😀'.repeat(300))

    expect(draftErrors(d).items).toEqual({})
  })

  it('needs at least one requirement', () => {
    const d = draft({ ...POSTING, required: [], preferred: [] })

    expect(draftErrors(d).requirements).toBeDefined()
    expect(hasDraftErrors(draftErrors(d))).toBe(true)
  })
})
