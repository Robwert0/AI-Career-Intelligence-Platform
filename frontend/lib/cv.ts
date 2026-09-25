// Hand-written from files/RobertMirea_CV2026.pdf (projects come from lib/projects.ts instead). When
// the PDF changes, update this file too: the chat answers from the ingested PDF, so drift shows up
// as contradictions.

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

export type SkillGroup = { name: string; skills: string[] }

export type Degree = { degree: string; school: string; period: string; note?: string }

export type Cv = {
  name: string
  initials: string
  title: string
  location: string
  photo?: { src: string; alt: string }
  links: Link[]
  summary: string
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
  summary:
    'Backend-focused software engineer building Python microservices on a high-scale, event-driven conversational AI platform. Hands-on with RabbitMQ, PostgreSQL/pgvector, Redis, Docker, and CI/CD, with production reliability ownership and comprehensive testing (unit, integration, end-to-end). Also experienced with Java/Spring Boot. Currently pursuing an MSc in Computer Science.',
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
    { name: 'Languages', skills: ['Java', 'Python', 'SQL', 'TypeScript', 'C++'] },
    {
      name: 'Backend',
      skills: [
        'Microservices',
        'Event-driven architecture',
        'RabbitMQ',
        'Redis',
        'PostgreSQL/pgvector',
        'Spring Boot',
        'FastAPI',
        'REST APIs',
        'Pydantic',
      ],
    },
    {
      name: 'Ops & Testing',
      skills: [
        'Docker',
        'CI/CD',
        'New Relic alerting',
        'Incident response',
        'Unit, integration & E2E testing',
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
      school:
        'Transilvania University of Brasov — Faculty of Electrical Engineering and Computer Science',
      period: '2021 – 2025',
      note: 'Thesis-level projects in robotics: 6-DOF robotic arm — CAD design (CATIA), Simulink simulation, forward/inverse kinematics control.',
    },
  ],
  languages: ['Romanian (native)', 'English (C1)'],
}
