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
  title: 'Software Engineer — Backend',
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
  headline: 'I build the backend services behind a real-time conversational AI platform.',
  intro:
    'I build and maintain services that run in production, and I own what happens after they ship: alerting, incident response, and debugging failures that cross service boundaries, backed by unit, integration and end-to-end tests. Before that I interned at BearingPoint and Synergo Applications, working in Python and Java.',
  glance: [
    { label: 'role', value: 'Software Engineer, Tyrell Corporation' },
    { label: 'core stack', value: 'Python · RabbitMQ · PostgreSQL · Redis · Docker' },
    { label: 'education', value: 'MSc student, Politehnica Bucharest' },
    { label: 'location', value: 'Bucharest, Romania' },
  ],
  summary:
    'Backend-focused software engineer building Python microservices on a high-scale, event-driven conversational AI platform. Hands-on with RabbitMQ, PostgreSQL/pgvector, Redis, Docker, and CI/CD, with production reliability ownership and comprehensive testing (unit, integration, end-to-end). Also experienced with Java/Spring Boot. Currently pursuing an MSc in Computer Science.',
  selectedWork: [
    {
      title: 'Generative image pipeline',
      employer: 'Tyrell Corporation',
      context: 'Employer work',
      period: '2025 – present',
      summary: 'Generates images for the platform by calling ML inference services.',
      problem:
        'Inference calls can fail, and every generation involves user credits and transactions that have to stay correct when they do.',
      contribution:
        'Developed the pipeline that integrates the ML inference services, including its failure handling.',
      decisions: [
        'Automatic recovery from failed inference requests.',
        'Credit and transaction integrity preserved when failures happen.',
      ],
      stack: ['Python', 'Microservices', 'Event-driven architecture', 'ML inference services'],
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
        'Hybrid retrieval: pgvector HNSW similarity combined with Postgres full-text ranking.',
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
      title: 'Software Engineer',
      company: 'Tyrell Corporation',
      location: 'Remote',
      period: 'Nov 2025 – Present',
      context:
        'High-scale, real-time conversational AI platform (microservices, event-driven architecture).',
      highlights: [
        'Build and maintain Python microservices in an event-driven architecture (RabbitMQ message broker, PostgreSQL/pgvector, Redis).',
        'Developed a generative image pipeline integrating ML inference services, with automatic failure recovery and credit/transaction integrity.',
        'Own production reliability: alerting (New Relic), incident response, and distributed-systems debugging across services.',
        'CI/CD, Docker, multi-service deployments; unit, integration, and end-to-end test suites.',
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
    { name: 'Languages', skills: ['Python', 'Java', 'TypeScript', 'SQL', 'C++'] },
    {
      name: 'Backend',
      skills: [
        'Microservices',
        'Event-driven architecture',
        'FastAPI',
        'Spring Boot',
        'REST APIs',
        'Pydantic',
        'SQLAlchemy',
      ],
    },
    { name: 'Data & messaging', skills: ['PostgreSQL', 'pgvector', 'Redis', 'RabbitMQ'] },
    {
      name: 'Infrastructure & operations',
      skills: ['Docker', 'CI/CD', 'New Relic alerting', 'Incident response', 'Git/GitHub'],
    },
    {
      name: 'Testing',
      skills: ['Unit testing', 'Integration testing', 'End-to-end testing', 'pytest'],
    },
    {
      name: 'AI & ML',
      skills: ['RAG pipelines', 'LLM integration', 'OpenCV', 'MediaPipe', 'scikit-learn'],
    },
    { name: 'Also used', skills: ['Next.js', 'React', 'MATLAB/Simulink', 'ROS'] },
  ],
  education: [
    {
      degree: 'MSc, Automatic Control and Computer Science',
      school: 'National University of Science and Technology Politehnica Bucharest',
      period: 'Oct 2025 – Present',
    },
    {
      degree: 'BSc, Robotics',
      school:
        'Transilvania University of Brasov — Faculty of Electrical Engineering and Computer Science',
      period: '2021 – 2025',
      note: 'Thesis-level projects in robotics: 6-DOF robotic arm — CAD design (CATIA), Simulink simulation, forward/inverse kinematics control.',
    },
  ],
  languages: ['Romanian (native)', 'English (C1)'],
}
