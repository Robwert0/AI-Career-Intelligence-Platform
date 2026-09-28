import { authedRequest } from './api'
import type { ApiResult } from './http'

export type Recovery = 'paste' | 'retry' | 'fix_url' | 'wait'
export type FailureOut = { code: string; message: string; recovery: Recovery }

export type Requirement = { text: string; sensitive: boolean }
export type JobPosting = {
  title: string
  company: string | null
  responsibilities: string[]
  required: Requirement[]
  preferred: Requirement[]
}

export type JobIntake = { url: string } | { text: string }
export type JobSubmitted = { job_id: string }
export type JobStatus = 'queued' | 'running' | 'done' | 'failed'
export type JobStage = 'reading' | 'extracting'
export type JobView = {
  job_id: string
  status: JobStatus
  stage: JobStage | null
  error: FailureOut | null
  posting: JobPosting | null
  source_url: string | null
  input_truncated: boolean
}

export type AnalysisStatus = 'queued' | 'running' | 'needs_decision' | 'done' | 'failed'
export type AnalysisStage =
  'reading_cv' | 'reading_github' | 'matching' | 'assessing' | 'scoring' | 'recommending'
export type CandidateSource = 'cv' | 'github'
export type Decision = { failed_source: CandidateSource; error: FailureOut }
export type AnalysisSubmitted = { analysis_id: string }
export type AnalysisView = {
  analysis_id: string
  status: AnalysisStatus
  stage: AnalysisStage | null
  queue_position: number | null
  error: FailureOut | null
  decision: Decision | null
  report: MatchReport | null
}

export type RequirementStatus =
  'demonstrated' | 'partial' | 'not_demonstrated' | 'unmet' | 'not_assessed'
export type Importance = 'required' | 'preferred'
export type EvidenceKind =
  'work' | 'project' | 'repo' | 'skill_list' | 'education' | 'accomplishment'
export type Evidence = {
  id: string
  source: CandidateSource
  kind: EvidenceKind
  section_label: string
  text: string
  url: string | null
}
export type AssessedRequirement = {
  id: string
  text: string
  importance: Importance
  status: RequirementStatus
  rationale: string
  hard_gap: boolean
  evidence: Evidence[]
}
export type BreakdownCategory = 'required' | 'preferred' | 'applied_evidence'
export type BreakdownRow = {
  category: BreakdownCategory
  weight: number
  effective_weight: number
  score: number
  points: number
}
export type SourceStatus = 'read' | 'not_provided' | 'failed' | 'skipped'
export type Coverage = {
  level: 'high' | 'medium' | 'low'
  cv: SourceStatus
  github: {
    status: SourceStatus
    inspected_repos: number
    public_non_fork_repos: number
    readmes_found: number
  }
  requirements_with_evidence: number
  limitations: string[]
}
export type Recommendation = { requirement_id: string; title: string; detail: string }
export type Rewrite = { evidence_id: string; before: string; after: string; questions: string[] }
export type Refusal = { reasons: string[]; needed: string[] }
export type MatchReport = {
  score: number | null
  refusal: Refusal | null
  summary: { strongest: string[]; gaps: string[] }
  breakdown: BreakdownRow[]
  coverage: Coverage
  requirements: AssessedRequirement[]
  recommendations: { immediate: Recommendation[]; longer_term: Recommendation[] }
  rewrites: Rewrite[]
  disclaimer: string
  model: string
}

// Up to 5 MB can take longer than the 10s default on a slow connection.
const UPLOAD_TIMEOUT_MS = 60_000

function post(body?: FormData | object): RequestInit {
  if (body === undefined) return { method: 'POST' }
  if (body instanceof FormData) {
    return { method: 'POST', body, signal: AbortSignal.timeout(UPLOAD_TIMEOUT_MS) }
  }
  return { method: 'POST', body: JSON.stringify(body) }
}

function analysisPath(analysisId: string, action = ''): string {
  return `/match/analyses/${encodeURIComponent(analysisId)}${action}`
}

export function submitJob(intake: JobIntake): Promise<ApiResult<JobSubmitted>> {
  return authedRequest<JobSubmitted>('/match/jobs', post(intake))
}

export function getJob(jobId: string): Promise<ApiResult<JobView>> {
  return authedRequest<JobView>(`/match/jobs/${encodeURIComponent(jobId)}`)
}

export function submitAnalysis(form: FormData): Promise<ApiResult<AnalysisSubmitted>> {
  return authedRequest<AnalysisSubmitted>('/match/analyses', post(form))
}

export function getAnalysis(analysisId: string): Promise<ApiResult<AnalysisView>> {
  return authedRequest<AnalysisView>(analysisPath(analysisId))
}

export function continueAnalysis(analysisId: string): Promise<ApiResult<AnalysisSubmitted>> {
  return authedRequest<AnalysisSubmitted>(analysisPath(analysisId, '/continue'), post())
}

export function retryAnalysis(
  analysisId: string,
  form?: FormData,
): Promise<ApiResult<AnalysisSubmitted>> {
  return authedRequest<AnalysisSubmitted>(analysisPath(analysisId, '/retry'), post(form))
}
