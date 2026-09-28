import { describe, expect, it } from 'vitest'
import type { JobPosting } from '../match'
import {
  buildAnalysisForm,
  buildCvRetryForm,
  candidateErrors,
  candidateSources,
  cvFileError,
  cvRetryError,
  DISCLOSURE,
  EMPTY_CANDIDATE,
  formatBytes,
  hasCandidateErrors,
  hasSource,
  isGithubProfileUrl,
  jobInputError,
  jobIntake,
  MAX_CV_BYTES,
  type CandidateInput,
  type JobInput,
} from '../matchInputs'

const POSTING: JobPosting = {
  title: 'Backend Engineer',
  company: null,
  responsibilities: [],
  required: [{ text: 'Go', sensitive: false }],
  preferred: [],
}
const CV_TEXT = 'Senior backend engineer. Built Go and Python services at Tyrell for five years.'
const PDF = new File(['%PDF-1.7'], 'cv.pdf', { type: 'application/pdf' })

function job(patch: Partial<JobInput>): JobInput {
  return { tab: 'url', url: '', text: '', ...patch }
}

function candidate(patch: Partial<CandidateInput> = {}): CandidateInput {
  return { ...EMPTY_CANDIDATE, ...patch }
}

describe('jobInputError', () => {
  it.each(['', '   ', 'not a link', 'ftp://jobs.example.com/1', 'jobs.example.com/1'])(
    'rejects the URL %j',
    (url) => {
      expect(jobInputError(job({ url }))).not.toBeNull()
    },
  )

  it('accepts a full https link', () => {
    expect(jobInputError(job({ url: ' https://jobs.example.com/1 ' }))).toBeNull()
  })

  it('checks only the active tab', () => {
    expect(jobInputError(job({ tab: 'text', url: 'nonsense', text: 'x'.repeat(50) }))).toBeNull()
  })

  it.each([
    ['x'.repeat(49), false],
    ['x'.repeat(50), true],
    ['x'.repeat(30_000), true],
    ['x'.repeat(30_001), false],
    [`${' '.repeat(100)}x`, false],
  ])('pasted text of %#', (text, valid) => {
    expect(jobInputError(job({ tab: 'text', text })) === null).toBe(valid)
  })

  it('counts characters as code points, like the backend', () => {
    expect(jobInputError(job({ tab: 'text', text: '😀'.repeat(50) }))).toBeNull()
    expect(jobInputError(job({ tab: 'text', text: '😀'.repeat(30_000) }))).toBeNull()
    expect(jobInputError(job({ tab: 'text', text: '😀'.repeat(25) }))).not.toBeNull()
  })
})

describe('jobIntake', () => {
  it('sends a trimmed URL for the URL tab', () => {
    expect(jobIntake(job({ url: ' https://a.example/1 ', text: 'ignored' }))).toEqual({
      url: 'https://a.example/1',
    })
  })

  it('sends trimmed text for the paste tab', () => {
    expect(jobIntake(job({ tab: 'text', url: 'ignored', text: '  body  ' }))).toEqual({
      text: 'body',
    })
  })
})

describe('cvFileError', () => {
  it.each(['cv.pdf', 'cv.PDF', 'cv.docx', 'My CV (final).Docx'])('accepts %s', (name) => {
    expect(cvFileError({ name, size: 1000 })).toBeNull()
  })

  it.each(['cv.docm', 'cv.doc', 'cv.txt', 'cv.pdf.exe', 'cv'])('rejects %s', (name) => {
    expect(cvFileError({ name, size: 1000 })).toBe('Choose a PDF or DOCX file.')
  })

  it('accepts exactly 5 MB and rejects one byte more', () => {
    expect(cvFileError({ name: 'cv.pdf', size: MAX_CV_BYTES })).toBeNull()
    expect(cvFileError({ name: 'cv.pdf', size: MAX_CV_BYTES + 1 })).toBe(
      'That file is larger than 5 MB.',
    )
  })

  it('rejects an empty file', () => {
    expect(cvFileError({ name: 'cv.pdf', size: 0 })).toBe('That file is empty.')
  })
})

describe('isGithubProfileUrl', () => {
  it.each([
    'https://github.com/octocat',
    'https://github.com/octocat/',
    'https://github.com/a-b',
    `https://github.com/${'a'.repeat(39)}`,
  ])('accepts %s', (url) => {
    expect(isGithubProfileUrl(url)).toBe(true)
  })

  it.each([
    'http://github.com/octocat',
    'https://github.com/',
    'https://github.com/octocat/repo',
    'https://github.com/octocat?tab=repositories',
    'https://gist.github.com/octocat',
    'https://github.com.evil.example/octocat',
    'https://github.com/-octocat',
    'https://github.com/a--b',
    `https://github.com/${'a'.repeat(40)}`,
    'github.com/octocat',
  ])('rejects %s', (url) => {
    expect(isGithubProfileUrl(url)).toBe(false)
  })
})

describe('candidate validation', () => {
  it('asks for a source until one is given', () => {
    expect(candidateErrors(candidate()).sources).toBeDefined()
    expect(candidateErrors(candidate({ cvFile: PDF })).sources).toBeUndefined()
    expect(
      candidateErrors(candidate({ githubUrl: 'https://github.com/octocat' })).sources,
    ).toBeUndefined()
  })

  it('counts only the active CV mode as a source', () => {
    const leftover = candidate({ cvMode: 'file', cvFile: null, cvText: CV_TEXT })

    expect(hasSource(leftover)).toBe(false)
    expect(candidateSources(candidate({ cvMode: 'text', cvText: CV_TEXT, cvFile: PDF }))).toEqual({
      cv: true,
      github: false,
    })
  })

  it('checks the pasted CV length', () => {
    expect(candidateErrors(candidate({ cvMode: 'text', cvText: 'too short' })).cv).toBeDefined()
    expect(candidateErrors(candidate({ cvMode: 'text', cvText: CV_TEXT })).cv).toBeUndefined()
  })

  it('checks the GitHub URL only when one is given', () => {
    expect(candidateErrors(candidate({ githubUrl: 'octocat' })).github).toBeDefined()
    expect(candidateErrors(candidate({ githubUrl: '  ' })).github).toBeUndefined()
  })

  it('requires consent', () => {
    expect(candidateErrors(candidate({ cvFile: PDF })).consent).toBeDefined()
    expect(hasCandidateErrors(candidateErrors(candidate({ cvFile: PDF, consent: true })))).toBe(
      false,
    )
  })
})

describe('buildAnalysisForm', () => {
  it('sends the job, the file, the GitHub URL and consent', () => {
    const form = buildAnalysisForm(
      POSTING,
      candidate({ cvFile: PDF, githubUrl: ' https://github.com/octocat ', consent: true }),
    )

    expect(JSON.parse(form.get('job') as string)).toEqual(POSTING)
    expect((form.get('cv') as File).name).toBe('cv.pdf')
    expect(form.get('github_url')).toBe('https://github.com/octocat')
    expect(form.get('consent')).toBe('true')
    expect(form.has('cv_text')).toBe(false)
  })

  it('sends only the active CV mode, never both', () => {
    const form = buildAnalysisForm(
      POSTING,
      candidate({ cvMode: 'text', cvFile: PDF, cvText: ` ${CV_TEXT} `, consent: true }),
    )

    expect(form.get('cv_text')).toBe(CV_TEXT)
    expect(form.has('cv')).toBe(false)
  })

  it('omits a blank GitHub URL', () => {
    const form = buildAnalysisForm(POSTING, candidate({ cvFile: PDF, consent: true }))

    expect(form.has('github_url')).toBe(false)
  })
})

describe('CV retry', () => {
  it('needs the CV again', () => {
    expect(cvRetryError(candidate())).not.toBeNull()
    expect(cvRetryError(candidate({ cvFile: PDF }))).toBeNull()
  })

  it('sends only the CV', () => {
    const form = buildCvRetryForm(candidate({ cvFile: PDF, githubUrl: 'https://github.com/x' }))

    expect([...form.keys()]).toEqual(['cv'])
  })
})

describe('formatBytes', () => {
  it.each([
    [512, '512 B'],
    [2048, '2 KB'],
    [1_572_864, '1.5 MB'],
  ])('%s → %s', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected)
  })
})

describe('DISCLOSURE', () => {
  it('matches the spec §6.5 text verbatim', () => {
    expect(DISCLOSURE).toBe(
      "Your CV is processed on this server by a locally hosted AI model and never leaves it. The job URL is fetched by our server. Public GitHub data is read through GitHub's API. Everything is deleted within an hour.",
    )
  })
})
