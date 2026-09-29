// Hand-written from files/RobertMirea_CV2026.pdf; projects come from lib/projects.ts, and the hero
// and selected-work copy is written from both. When the PDF changes, update this file too: the chat
// answers from the ingested PDF, so drift shows up as contradictions.

import { projects, type Project } from './projects'

export type Link = { name: 'Email' | 'GitHub' | 'LinkedIn'; label: string; href: string }

export type Role = {
  title: string
  company: string
  location: string
  period: string
  context?: string
  highlights: string[]
}

export type Fact = { label: string; value: string }

export type SelectedWork = {
  title: string
  employer?: string
  context: string
  period: string
  summary: string
  problem: string
  contribution: string
  decisions: string[]
  outcome?: string
  stack: string[]
  projectSlug?: string
}

export type SkillGroup = { name: string; skills: string[] }

export type Degree = { degree: string; school: string; period: string; note?: string }

export type Cv = {
  name: string
  initials: string
  title: string
  location: string
  photo?: { src: string; alt: string }
  pdf?: { href: string }
  links: Link[]
  headline: string
  intro: string
  glance: Fact[]
  summary: string
  selectedWork: SelectedWork[]
  experience: Role[]
  projects: Project[]
  skills: SkillGroup[]
  education: Degree[]
  languages: string[]
}

export const cv: Cv = {
  name: 'Robert Mirea',
  initials: 'RM',
  title: 'Backend & AI Engineer',
  location: 'Bucharest, Romania',
  links: [
    { name: 'Email', label: 'mirearobert32@gmail.com', href: 'mailto:mirearobert32@gmail.com' },
    { name: 'GitHub', label: 'github.com/Robwert0', href: 'https://github.com/Robwert0' },
    {
      name: 'LinkedIn',
      label: 'linkedin.com/in/robert-mirea',
      href: 'https://www.linkedin.com/in/robert-mirea-413a91222',
    },
  ],
  headline: 'I build the backend and LLM features of a multi-tenant conversational AI platform.',
  intro:
    'I own features end to end, from the database migration to the product, and the parts that have to hold up in production: LLM reliability, security and payment correctness, backed by on-call and unit, integration and end-to-end tests. Before that I interned at BearingPoint and Synergo Applications, working in Python and Java.',
  glance: [
    { label: 'role', value: 'Junior Software Engineer, Tyrell Corporation' },
    { label: 'core stack', value: 'Python · FastAPI · PostgreSQL · Redis · RabbitMQ · Celery' },
    { label: 'education', value: 'MSc student, Politehnica Bucharest' },
    { label: 'location', value: 'Bucharest, Romania' },
  ],
  summary:
    'Backend and AI engineer on a multi-tenant conversational AI platform built on Python/FastAPI microservices, RabbitMQ, Celery, PostgreSQL and Redis. Owns features end to end, plus LLM reliability (multi-provider failover, guardrails, Langfuse observability), security and payment correctness. Builds agentic developer tooling (Claude Code skills, automation pipelines) and RAG systems. Also experienced with Java/Spring Boot.',
  selectedWork: [
    {
      title: 'LLM engine',
      employer: 'Tyrell Corporation',
      context: 'Employer work',
      period: '2025 – present',
      summary: 'The layer that calls the language models behind the platform’s conversations.',
      problem:
        'Generation can get stuck repeating itself or break persona, and moderation has to be traceable.',
      contribution:
        'Built a provider-agnostic AI client factory and the reliability checks around generation.',
      decisions: [
        'Post-generation repetition-loop detection with provider failover.',
        'Persona-break leaks suppressed.',
        'Image guard-rail decoupled from chat.',
        'Moderation linked to Langfuse traces and scores.',
      ],
      stack: ['Python', 'FastAPI', 'Microservices', 'Langfuse'],
    },
    {
      title: 'AI Career Intelligence Platform',
      context: 'Personal project',
      period: '2026 – present',
      summary:
        'This site: a chat that answers questions about my CV and cites the passages it used.',
      problem:
        'A CV cannot answer follow-up questions, and a model that answers for it must not be steerable by what visitors type.',
      contribution: 'Designed and built the backend, the retrieval pipeline and the frontend.',
      decisions: [
        'Hybrid retrieval: pgvector similarity and Postgres full-text, fused with Reciprocal Rank Fusion.',
        'System prompt, visitor input and retrieved CV text kept in separate channels; chat-template tokens escaped.',
        'Refresh tokens rotate on every use, and reuse revokes the whole token family.',
        'Redis rate limits per IP and per user that fail closed.',
      ],
      outcome:
        'Works end to end on my real CV, with 370+ backend tests and a security review on every auth or AI-input change.',
      stack: ['FastAPI', 'PostgreSQL/pgvector', 'Redis', 'Next.js', 'TypeScript'],
      projectSlug: 'ai-career-intelligence-platform',
    },
    {
      title: 'Jarvis',
      context: 'Personal project',
      period: '2026',
      summary:
        'A desktop voice assistant that opens apps, runs macros, searches the web and controls the system.',
      problem: 'Everyday desktop actions still need hands on the keyboard.',
      contribution: 'Built the Electron app, the FastAPI agent service and the local tools.',
      decisions: [
        'Two LLM paths share one toolset: an ElevenLabs agent drives voice, a server-side Claude tool-use loop drives text.',
        'Tools execute locally in the Python process, with cooperative cancellation of in-flight actions.',
        'Long-term memories stored in SQLite and injected into every text and voice session.',
      ],
      outcome: 'Feature-complete for daily use in July 2026, with a pytest suite running in CI.',
      stack: ['Python', 'FastAPI', 'Claude API', 'ElevenLabs', 'Electron', 'React'],
      projectSlug: 'jarvis',
    },
    {
      title: 'Price Comparator',
      context: 'Internship application challenge',
      period: '2025',
      summary: 'A REST backend that compares grocery prices across Lidl, Kaufland and Profi.',
      problem:
        'Prices differ between stores, and different package sizes make direct comparison misleading.',
      contribution: 'Built the Spring Boot service end to end.',
      decisions: [
        'A basket optimizer that splits a shopping list across stores to find the cheapest combination.',
        'Recommendations by price per kg or litre, so package sizes compare fairly.',
        'Price alerts checked by a scheduled job and delivered by email; retailer data loaded from CSV.',
      ],
      stack: ['Java', 'Spring Boot', 'REST APIs', 'OpenCSV', 'Spring Mail'],
      projectSlug: 'price-comparator',
    },
    {
      title: 'Employee data validation',
      employer: 'BearingPoint',
      context: 'Internship',
      period: '2024',
      summary: 'Validates employee records, stores them in PostgreSQL and exports clean data.',
      problem: 'Employee records arrived with inconsistent formats, duplicates and invalid values.',
      contribution: 'Built the application, from the validation models to storage and export.',
      decisions: [
        'Pydantic validators for each rule, including checking a personal numeric code (CNP) against the stated gender.',
        'Duplicate prevention on employee ID before records are appended.',
      ],
      stack: ['Python', 'Pydantic', 'PostgreSQL'],
      projectSlug: 'employee-data-validator',
    },
  ],
  experience: [
    {
      title: 'Junior Software Engineer',
      company: 'Tyrell Corporation',
      location: 'Remote',
      period: 'Nov 2025 – Present',
      context:
        'Multi-tenant conversational AI platform (Python/FastAPI microservices, event-driven architecture).',
      highlights: [
        'Own features end to end, from DB migration to backoffice to product: a character builder with ComfyUI-generated portraits, ElevenLabs text-to-speech, companion discovery, and a payment-gated referral program.',
        'LLM engine: built a provider-agnostic AI client factory; post-generation repetition-loop detection with provider failover; suppressed persona-break leaks; decoupled the image guard-rail from chat; linked moderation to Langfuse traces and scores.',
        'Engineering enablement: built AI-agent tooling for the team — Claude Code skills, automation pipelines, and repo conventions.',
        'Security and payments: fixed cross-user IDOR vulnerabilities; hardened the payment integration (callback amount/currency validation, pending payment persisted before the provider call).',
        'Data and reliability: zero-downtime column rename (expand → switch readers → contract); fixed schema drift and full-table scans; durable messaging (persistent publishing, dead-letter logging, Celery retries).',
        'On-call and incident response (New Relic, Sentry, PagerDuty); CI/CD, Docker; pytest unit, integration, and end-to-end suites.',
      ],
    },
    {
      title: 'Software Developer (Internship)',
      company: 'BearingPoint',
      location: 'Brasov',
      period: 'Jun 2024 – Aug 2024',
      highlights: [
        'Built a Python application to manage and validate employee records, enforcing strict data formats and constraints.',
        'Used Pydantic for schema validation and PostgreSQL for storage; implemented duplicate prevention and structured exports for downstream analysis.',
      ],
    },
    {
      title: 'Application Developer (Internship)',
      company: 'Synergo Applications',
      location: 'Brasov',
      period: 'Aug 2023 – Sep 2023',
      highlights: [
        'Designed and implemented a land registry management application in Java, applying OOP design principles to model ownership records and property transactions.',
      ],
    },
  ],
  projects,
  skills: [
    { name: 'Languages', skills: ['Python', 'Java', 'SQL', 'TypeScript', 'C++'] },
    {
      name: 'Backend',
      skills: [
        'Microservices',
        'Event-driven architecture',
        'FastAPI',
        'SQLAlchemy/Alembic',
        'RabbitMQ',
        'Celery',
        'Redis',
        'PostgreSQL/pgvector',
        'Spring Boot',
        'REST APIs',
        'Pydantic',
      ],
    },
    {
      name: 'AI / LLM',
      skills: [
        'LLM APIs (Claude, Gemini, open-weight via Ollama)',
        'Multi-provider failover',
        'RAG and hybrid retrieval',
        'Guardrails and moderation',
        'Langfuse',
        'ComfyUI',
        'ElevenLabs',
        'Claude Code',
      ],
    },
    {
      name: 'Ops & Testing',
      skills: [
        'Docker',
        'CI/CD',
        'Heroku',
        'Cloudflare R2',
        'New Relic',
        'Sentry',
        'PagerDuty',
        'Incident response',
        'pytest (unit, integration, e2e)',
        'ruff',
        'mypy/pyright',
      ],
    },
    {
      name: 'Tools & Other',
      skills: [
        'Git/GitHub',
        'OpenCV',
        'MediaPipe',
        'scikit-learn',
        'React',
        'Next.js',
        'MATLAB/Simulink',
        'ROS',
      ],
    },
  ],
  education: [
    {
      degree: 'MSc, Automatic Control and Computer Science',
      school: 'National University of Science and Technology Politehnica Bucharest',
      period: 'Oct 2025 – Present',
    },
    {
      degree: 'BSc, Robotics',
      school: 'Transilvania University of Brasov',
      period: '2021 – 2025',
      note: 'Coursework: 6-DOF robotic arm (CATIA CAD, Simulink simulation, forward/inverse kinematics).',
    },
  ],
  languages: ['Romanian (native)', 'English (C1)'],
}
