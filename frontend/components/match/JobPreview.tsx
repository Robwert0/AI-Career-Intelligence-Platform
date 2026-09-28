'use client'

import { useState } from 'react'
import { describedBy } from '@/lib/aria'
import {
  addItem,
  draftErrors,
  hasDraftErrors,
  isFull,
  MAX_ITEMS,
  moveItem,
  otherList,
  removeItem,
  SENSITIVE_PREVIEW_NOTE,
  updateItem,
  type DraftErrors,
  type DraftList,
  type JobDraft,
} from '@/lib/jobDraft'
import { useFocusAfterRender } from '@/lib/useFocusAfterRender'
import { FieldError } from './Field'
import { FIELD, LABEL, PRIMARY_BUTTON, SECONDARY_BUTTON, TEXT_BUTTON } from './styles'

const LIST_TITLE: Record<DraftList, string> = {
  responsibilities: 'Responsibilities',
  required: 'Required',
  preferred: 'Preferred',
}
const ADD_LABEL: Record<DraftList, string> = {
  responsibilities: 'Add a responsibility',
  required: 'Add a required requirement',
  preferred: 'Add a preferred requirement',
}
const LISTS: DraftList[] = ['responsibilities', 'required', 'preferred']
const NO_ERRORS: DraftErrors = { items: {} }

type Props = {
  draft: JobDraft
  inputTruncated: boolean
  onChange: (draft: JobDraft) => void
  onConfirm: () => void
  onDiscard: () => void
}

export function JobPreview({ draft, inputTruncated, onChange, onConfirm, onDiscard }: Props) {
  const [attempted, setAttempted] = useState(false)
  const focusAfterRender = useFocusAfterRender()
  const errors = draftErrors(draft)
  const shown = attempted ? errors : NO_ERRORS

  function confirm() {
    setAttempted(true)
    if (!hasDraftErrors(errors)) {
      onConfirm()
      return
    }
    const firstItem = Object.keys(errors.items)[0]
    const target = errors.title
      ? 'job-title'
      : errors.company
        ? 'job-company'
        : firstItem
          ? `item-${firstItem}`
          : 'add-required'
    document.getElementById(target)?.focus()
  }

  return (
    <div className="space-y-8">
      {inputTruncated ? (
        <p className="rounded-md border border-line px-4 py-3 text-sm text-muted">
          The description was longer than 30,000 characters, so only the first part was read. Check
          that nothing important is missing.
        </p>
      ) : null}
      <p className="text-sm text-muted">
        Check what we extracted. Fix anything that is wrong, move items between required and
        preferred, and remove anything that does not belong. The analysis uses exactly this list.
      </p>
      <p className="text-sm text-muted">{SENSITIVE_PREVIEW_NOTE}</p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor="job-title" className={LABEL}>
            Job title
          </label>
          <input
            id="job-title"
            value={draft.title}
            onChange={(event) => onChange({ ...draft, title: event.target.value })}
            aria-invalid={shown.title !== undefined}
            aria-describedby={describedBy(shown.title && 'job-title-error')}
            className={FIELD}
          />
          <FieldError id="job-title-error" message={shown.title} />
        </div>
        <div className="space-y-2">
          <label htmlFor="job-company" className={LABEL}>
            Company (optional)
          </label>
          <input
            id="job-company"
            value={draft.company}
            onChange={(event) => onChange({ ...draft, company: event.target.value })}
            aria-invalid={shown.company !== undefined}
            aria-describedby={describedBy(shown.company && 'job-company-error')}
            className={FIELD}
          />
          <FieldError id="job-company-error" message={shown.company} />
        </div>
      </div>

      {LISTS.map((list) => (
        <ItemList
          key={list}
          list={list}
          draft={draft}
          errors={shown}
          onChange={onChange}
          focusAfterRender={focusAfterRender}
        />
      ))}

      <FieldError id="requirements-error" message={shown.requirements} />

      <div className="flex flex-wrap items-center gap-4">
        <button type="button" onClick={confirm} className={PRIMARY_BUTTON}>
          Continue to your evidence
        </button>
        <button type="button" onClick={onDiscard} className={TEXT_BUTTON}>
          Use a different job
        </button>
      </div>
    </div>
  )
}

type ItemListProps = {
  list: DraftList
  draft: JobDraft
  errors: DraftErrors
  onChange: (draft: JobDraft) => void
  focusAfterRender: (id: string) => void
}

function ItemList({ list, draft, errors, onChange, focusAfterRender }: ItemListProps) {
  const items = draft[list]
  const title = LIST_TITLE[list]
  const movable = list === 'responsibilities' ? null : list
  const target = movable === null ? null : otherList(movable)

  function add() {
    const key = crypto.randomUUID()
    onChange(addItem(draft, list, key))
    focusAfterRender(`item-${key}`)
  }

  function remove(key: string) {
    onChange(removeItem(draft, list, key))
    focusAfterRender(`add-${list}`)
  }

  return (
    <fieldset className="space-y-3">
      <legend className="font-medium">
        {title}{' '}
        <span className="font-mono text-xs font-normal text-muted">
          ({items.length} of {MAX_ITEMS})
        </span>
      </legend>
      {items.length === 0 ? <p className="text-sm text-muted">None listed.</p> : null}
      <ol className="space-y-4">
        {items.map((item, index) => {
          const id = `item-${item.key}`
          const error = errors.items[item.key]
          const name = `${title} item ${index + 1}`
          return (
            <li key={item.key} className="space-y-2">
              <label htmlFor={id} className="sr-only">
                {name}
              </label>
              <textarea
                id={id}
                rows={2}
                value={item.text}
                onChange={(event) =>
                  onChange(updateItem(draft, list, item.key, event.target.value))
                }
                aria-invalid={error !== undefined}
                aria-describedby={describedBy(
                  item.sensitive && `${id}-sensitive`,
                  error && `${id}-error`,
                )}
                className={`${FIELD} field-sizing-content min-h-10 resize-y`}
              />
              {item.sensitive ? (
                <p
                  id={`${id}-sensitive`}
                  className="inline-flex items-center gap-1.5 rounded-sm border border-accent px-2 py-0.5 font-mono text-xs text-accent"
                >
                  <span aria-hidden="true">!</span>
                  Personal characteristic: not assessed. Confirm it yourself.
                </p>
              ) : null}
              <FieldError id={`${id}-error`} message={error} />
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {movable !== null && target !== null ? (
                  <button
                    type="button"
                    onClick={() => {
                      onChange(moveItem(draft, movable, item.key))
                      focusAfterRender(id)
                    }}
                    disabled={isFull(draft, target)}
                    aria-label={`Move to ${target}: ${name}`}
                    className={TEXT_BUTTON}
                  >
                    Move to {target}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => remove(item.key)}
                  aria-label={`Remove: ${name}`}
                  className={TEXT_BUTTON}
                >
                  Remove
                </button>
              </div>
            </li>
          )
        })}
      </ol>
      <button
        id={`add-${list}`}
        type="button"
        onClick={add}
        disabled={isFull(draft, list)}
        className={SECONDARY_BUTTON}
      >
        {ADD_LABEL[list]}
      </button>
    </fieldset>
  )
}
