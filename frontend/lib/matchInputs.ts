import type { JobIntake, JobPosting } from './match'
import { DEFAULT_UPLOAD_LIMITS, type UploadLimits } from './matchConfig'
import { charCount } from './text'

export const MIN_JOB_TEXT_CHARS = 50
export const MAX_JOB_TEXT_CHARS = 30_000
export const CV_ACCEPT =
  '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
export const DISCLOSURE =
  "Your CV is processed on this server by a locally hosted AI model and never leaves it. The job URL is fetched by our server. Public GitHub data is read through GitHub's API. Everything is deleted within an hour."

const CV_EXTENSIONS = ['.pdf', '.docx']
const GITHUB_PROFILE =
  /^https:\/\/github\.com\/[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}\/?$/

export type JobTab = 'url' | 'text'
export type JobInput = { tab: JobTab; url: string; text: string }
export const EMPTY_JOB_INPUT: JobInput = { tab: 'url', url: '', text: '' }

export type CvMode = 'file' | 'text'
export type CandidateInput = {
  cvMode: CvMode
  cvFile: File | null
  cvText: string
  githubUrl: string
  consent: boolean
}
export const EMPTY_CANDIDATE: CandidateInput = {
  cvMode: 'file',
  cvFile: null,
  cvText: '',
  githubUrl: '',
  consent: false,
}
export type CandidateErrors = { sources?: string; cv?: string; github?: string; consent?: string }

type ActiveCv = { file: File } | { text: string }

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function jobInputError(input: JobInput): string | null {
  if (input.tab === 'url') {
    const url = input.url.trim()
    if (url === '') return 'Enter the link to the job posting.'
    return isHttpUrl(url) ? null : 'Enter a full link, starting with https://'
  }
  const count = charCount(input.text.trim())
  if (count < MIN_JOB_TEXT_CHARS) {
    return `Paste at least ${MIN_JOB_TEXT_CHARS} characters of the job description.`
  }
  if (count > MAX_JOB_TEXT_CHARS) {
    return 'The description is over 30,000 characters. Paste only the job description itself.'
  }
  return null
}

export function jobIntake(input: JobInput): JobIntake {
  return input.tab === 'url' ? { url: input.url.trim() } : { text: input.text.trim() }
}

export function cvFileError(
  file: { name: string; size: number },
  limits: UploadLimits = DEFAULT_UPLOAD_LIMITS,
): string | null {
  const name = file.name.toLowerCase()
  if (!CV_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'Choose a PDF or DOCX file.'
  }
  if (file.size === 0) return 'That file is empty.'
  if (file.size > limits.maxCvBytes) {
    return `That file is larger than ${formatBytes(limits.maxCvBytes)}.`
  }
  return null
}

export function isGithubProfileUrl(value: string): boolean {
  return GITHUB_PROFILE.test(value)
}

function activeCv(input: CandidateInput): ActiveCv | null {
  if (input.cvMode === 'file') return input.cvFile === null ? null : { file: input.cvFile }
  const text = input.cvText.trim()
  return text === '' ? null : { text }
}

export function candidateSources(input: CandidateInput): { cv: boolean; github: boolean } {
  return { cv: activeCv(input) !== null, github: input.githubUrl.trim() !== '' }
}

export function hasSource(input: CandidateInput): boolean {
  const sources = candidateSources(input)
  return sources.cv || sources.github
}

function cvError(input: CandidateInput, limits: UploadLimits): string | null {
  const cv = activeCv(input)
  if (cv === null) return null
  if ('file' in cv) return cvFileError(cv.file, limits)
  const count = charCount(cv.text)
  if (count < limits.minCvTextChars) {
    return `Paste at least ${limits.minCvTextChars} characters of your CV.`
  }
  if (count > limits.maxCvTextChars) {
    return `Your CV text is over ${limits.maxCvTextChars.toLocaleString('en-US')} characters. Paste the main sections only.`
  }
  return null
}

export function candidateErrors(
  input: CandidateInput,
  limits: UploadLimits = DEFAULT_UPLOAD_LIMITS,
): CandidateErrors {
  const errors: CandidateErrors = {}
  if (!hasSource(input)) {
    errors.sources = 'Add a CV (a file or pasted text) or a GitHub profile to continue.'
  }
  const cv = cvError(input, limits)
  if (cv !== null) errors.cv = cv
  const github = input.githubUrl.trim()
  if (github !== '' && !isGithubProfileUrl(github)) {
    errors.github = 'Use your profile link, like https://github.com/your-username'
  }
  if (!input.consent) errors.consent = 'Tick the box to agree before analysing.'
  return errors
}

export function hasCandidateErrors(errors: CandidateErrors): boolean {
  return Object.keys(errors).length > 0
}

function appendCv(form: FormData, input: CandidateInput): void {
  const cv = activeCv(input)
  if (cv === null) return
  if ('file' in cv) form.append('cv', cv.file, cv.file.name)
  else form.append('cv_text', cv.text)
}

export function buildAnalysisForm(posting: JobPosting, input: CandidateInput): FormData {
  const form = new FormData()
  form.append('job', JSON.stringify(posting))
  appendCv(form, input)
  const github = input.githubUrl.trim()
  if (github !== '') form.append('github_url', github)
  form.append('consent', String(input.consent))
  return form
}

export function cvRetryError(
  input: CandidateInput,
  limits: UploadLimits = DEFAULT_UPLOAD_LIMITS,
): string | null {
  if (activeCv(input) === null) return 'Choose your CV file again, or paste its text.'
  return cvError(input, limits)
}

export function buildCvRetryForm(input: CandidateInput): FormData {
  const form = new FormData()
  appendCv(form, input)
  return form
}

export function githubRetryError(url: string): string | null {
  const trimmed = url.trim()
  if (trimmed === '') return 'Enter your GitHub profile link.'
  if (!isGithubProfileUrl(trimmed)) {
    return 'Use your profile link, like https://github.com/your-username'
  }
  return null
}

export function buildGithubRetryForm(url: string): FormData {
  const form = new FormData()
  form.append('github_url', url.trim())
  return form
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  const megabytes = bytes / (1024 * 1024)
  return `${Number.isInteger(megabytes) ? megabytes : megabytes.toFixed(1)} MB`
}
