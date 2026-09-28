import type { JobPosting, Requirement } from './match'
import { charCount } from './text'

export const MAX_ITEMS = 40
export const MAX_ITEM_CHARS = 300
export const MAX_TITLE_CHARS = 200

export type RequirementList = 'required' | 'preferred'
export type DraftList = 'responsibilities' | RequirementList
export type DraftItem = { key: string; text: string; sensitive: boolean }
export type JobDraft = {
  title: string
  company: string
  responsibilities: DraftItem[]
  required: DraftItem[]
  preferred: DraftItem[]
}
export type DraftErrors = {
  title?: string
  company?: string
  requirements?: string
  items: Record<string, string>
}

function draftItems(requirements: Requirement[], newKey: () => string): DraftItem[] {
  return requirements.map((requirement) => ({
    key: newKey(),
    text: requirement.text,
    sensitive: requirement.sensitive,
  }))
}

export function toDraft(posting: JobPosting, newKey: () => string): JobDraft {
  return {
    title: posting.title,
    company: posting.company ?? '',
    responsibilities: posting.responsibilities.map((text) => ({
      key: newKey(),
      text,
      sensitive: false,
    })),
    required: draftItems(posting.required, newKey),
    preferred: draftItems(posting.preferred, newKey),
  }
}

function filled(items: DraftItem[]): DraftItem[] {
  return items
    .map((item) => ({ ...item, text: item.text.trim() }))
    .filter((item) => item.text !== '')
}

function requirements(items: DraftItem[]): Requirement[] {
  return filled(items).map(({ text, sensitive }) => ({ text, sensitive }))
}

export function toPosting(draft: JobDraft): JobPosting {
  const company = draft.company.trim()
  return {
    title: draft.title.trim(),
    company: company === '' ? null : company,
    responsibilities: filled(draft.responsibilities).map((item) => item.text),
    required: requirements(draft.required),
    preferred: requirements(draft.preferred),
  }
}

export function isFull(draft: JobDraft, list: DraftList): boolean {
  return draft[list].length >= MAX_ITEMS
}

export function addItem(draft: JobDraft, list: DraftList, key: string): JobDraft {
  if (isFull(draft, list)) return draft
  return { ...draft, [list]: [...draft[list], { key, text: '', sensitive: false }] }
}

export function updateItem(draft: JobDraft, list: DraftList, key: string, text: string): JobDraft {
  return {
    ...draft,
    [list]: draft[list].map((item) => (item.key === key ? { ...item, text } : item)),
  }
}

export function removeItem(draft: JobDraft, list: DraftList, key: string): JobDraft {
  return { ...draft, [list]: draft[list].filter((item) => item.key !== key) }
}

export function otherList(list: RequirementList): RequirementList {
  return list === 'required' ? 'preferred' : 'required'
}

export function moveItem(draft: JobDraft, from: RequirementList, key: string): JobDraft {
  const to = otherList(from)
  const item = draft[from].find((candidate) => candidate.key === key)
  if (item === undefined || isFull(draft, to)) return draft
  return {
    ...draft,
    [from]: draft[from].filter((candidate) => candidate.key !== key),
    [to]: [...draft[to], item],
  }
}

export function draftErrors(draft: JobDraft): DraftErrors {
  const errors: DraftErrors = { items: {} }
  const title = draft.title.trim()
  if (title === '') errors.title = 'Add the job title.'
  else if (charCount(title) > MAX_TITLE_CHARS) {
    errors.title = `Keep the title to ${MAX_TITLE_CHARS} characters or fewer.`
  }
  if (charCount(draft.company.trim()) > MAX_TITLE_CHARS) {
    errors.company = `Keep the company name to ${MAX_TITLE_CHARS} characters or fewer.`
  }
  for (const item of [...draft.responsibilities, ...draft.required, ...draft.preferred]) {
    if (charCount(item.text.trim()) > MAX_ITEM_CHARS) {
      errors.items[item.key] = `Keep this to ${MAX_ITEM_CHARS} characters or fewer.`
    }
  }
  const posting = toPosting(draft)
  if (posting.required.length + posting.preferred.length === 0) {
    errors.requirements = 'Add at least one required or preferred requirement.'
  }
  return errors
}

export function hasDraftErrors(errors: DraftErrors): boolean {
  return (
    errors.title !== undefined ||
    errors.company !== undefined ||
    errors.requirements !== undefined ||
    Object.keys(errors.items).length > 0
  )
}
