// Hand-written from files/RobertMirea_CV2026.pdf; projects come from lib/projects.ts, and the hero
// and selected-work copy is written from both. When the PDF changes, update this file too: the chat
// answers from the ingested PDF, so drift shows up as contradictions.

import { projects, type Project } from './projects'

export type Link = { label: string; href: string }

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
  context: string
  period: string
  problem: string
  contribution: string
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
    { label: 'mirearobert32@gmail.com', href: 'mailto:mirearobert32@gmail.com' },
    { label: 'github.com/Robwert0', href: 'https://github.com/Robwert0' },
    {
      label: 'linkedin.com/in/robert-mirea',
      href: 'https://www.linkedin.com/in/robert-mirea-413a91222',
    },
  ],
  headline: 'I build the backend services behind a real-time conversational AI platform.',
  intro:
    'Software engineer at Tyrell Corporation, writing Python microservices in an event-driven architecture — RabbitMQ, PostgreSQL/pgvector and Redis — and owning their reliability in production. Also at home in Java and Spring Boot, and studying for an MSc in Automatic Control and Computer Science.',
  glance: [
    { label: 'now', value: 'Software Engineer, Tyrell Corporation' },
    { label: 'focus', value: 'Python microservices · event-driven systems · conversational AI' },
    { label: 'stack', value: 'Python · RabbitMQ · PostgreSQL/pgvector · Redis · Docker' },
    { label: 'studying', value: 'MSc, Politehnica Bucharest' },
    { label: 'based in', value: 'Bucharest, Romania' },
  ],
  summary:
    'Backend-focused software engineer building Python microservices on a high-scale, event-driven conversational AI platform. Hands-on with RabbitMQ, PostgreSQL/pgvector, Redis, Docker, and CI/CD, with production reliability ownership and comprehensive testing (unit, integration, end-to-end). Also experienced with Java/Spring Boot. Currently pursuing an MSc in Computer Science.',
  selectedWork: [
    {
      title: 'Generative image pipeline',
      context: 'At Tyrell Corporation',
      period: '2025 – present',
      problem:
        'Image generation depends on ML inference services that can fail mid-request, and each generation is tied to user credits and transactions.',
      contribution:
        'Developed the pipeline integrating the ML inference services, with automatic failure recovery and credit/transaction integrity.',
      stack: ['Python', 'Microservices', 'Event-driven architecture', 'ML inference services'],
    },
    {
      title: 'AI Career Intelligence Platform',
      context: 'Personal project',
      period: '2026 – present',
      problem:
        'A CV is a static document; recruiters cannot ask it follow-up questions, and an LLM that answers about it must not be steerable by what users type.',
      contribution:
        'Designed and built this site end to end: CV ingestion into pgvector, hybrid retrieval, a hardened generation prompt, JWT auth with rotating refresh tokens, and Redis rate limiting.',
      outcome:
        '370+ backend tests; every auth, rate-limit and AI-input change security-reviewed before merge.',
      stack: ['FastAPI', 'PostgreSQL/pgvector', 'Redis', 'Next.js', 'TypeScript'],
      projectSlug: 'ai-career-intelligence-platform',
    },
    {
      title: 'Jarvis',
      context: 'Personal project',
      period: '2026',
      problem:
        'Everyday desktop actions — opening apps, running a set of them together, searching the web — still need hands on the keyboard.',
      contribution:
        'Built a desktop voice assistant: an ElevenLabs voice loop with barge-in, a FastAPI Claude tool-use loop, and six local tools shared by voice and text.',
      outcome: 'Feature-complete for daily use in July 2026, with a pytest suite running in CI.',
      stack: ['Python', 'FastAPI', 'Claude API', 'ElevenLabs', 'Electron', 'React'],
      projectSlug: 'jarvis',
    },
    {
      title: 'Price Comparator',
      context: 'Internship application challenge',
      period: '2025',
      problem:
        'Grocery prices differ across Lidl, Kaufland and Profi, and package sizes make direct comparison misleading.',
      contribution:
        'Built a Spring Boot REST backend: cheapest-basket optimization across stores, discount and price-history tracking, scheduled email price alerts, and unit-price recommendations.',
      stack: ['Java', 'Spring Boot', 'REST APIs', 'Spring Mail'],
      projectSlug: 'price-comparator',
    },
    {
      title: 'Employee data validation',
      context: 'At BearingPoint · internship',
      period: '2024',
      problem:
        'Employee records arrived in inconsistent formats, with duplicates and invalid values.',
      contribution:
        'Built a Python application that validates every record with Pydantic, prevents duplicates, stores results in PostgreSQL and produces structured exports for analysis.',
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
