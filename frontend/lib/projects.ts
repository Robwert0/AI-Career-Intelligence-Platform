// Written from each repo's code, not its README: several READMEs claim things the code doesn't do.

export type ProjectCategory = 'flagship' | 'featured' | 'internship' | 'learning'

export type Project = {
  slug: string
  name: string
  tagline: string
  category: ProjectCategory
  context: string
  period: string
  purpose: string
  description: string
  stack: string[]
  highlights: string[]
  repos: string[]
}

export const projects: Project[] = [
  {
    slug: 'ai-career-intelligence-platform',
    name: 'AI Career Intelligence Platform',
    tagline:
      'This site: a RAG chat over my CV, with auth, rate limiting and prompt-injection defense',
    category: 'flagship',
    context: 'Personal project',
    period: 'Jun 2026 – present',
    purpose:
      'An interactive "AI version of my CV": visitors read the CV and ask it questions, and a retrieval-augmented model answers from the CV itself, citing the passages it used.',
    description:
      'A monorepo with a FastAPI backend and a Next.js frontend that talk over HTTP only. The CV PDF is parsed, chunked by section, embedded and stored in PostgreSQL with pgvector; each question runs hybrid retrieval and a local LLM answers from the retrieved chunks. Built as a production system rather than a demo: every feature ships with tests and goes through a security review before it merges.',
    stack: [
      'Python',
      'FastAPI',
      'SQLAlchemy 2.0 (async)',
      'PostgreSQL',
      'pgvector',
      'Redis',
      'sentence-transformers',
      'Ollama',
      'Next.js',
      'TypeScript',
      'Tailwind CSS',
      'Docker',
    ],
    highlights: [
      'RAG pipeline: PDF parsing into section-aware chunks, bge-small embeddings, and hybrid retrieval that combines HNSW cosine search with Postgres full-text ranking.',
      'Auth with short-lived JWT access tokens and rotating refresh tokens in an httpOnly, SameSite=Strict cookie; bcrypt hashing; reuse detection revokes the whole token family.',
      'Redis rate limiting per IP and per user that fails closed, applied to login, registration and chat.',
      'Prompt-injection defense: user text, retrieved CV text and the system prompt stay in separate channels; chat-template special tokens are escaped; answers are validated before they are returned.',
      'Phone numbers redacted at ingestion, strict CSP and security headers, and a layered backend (routes → services → repositories) with 370+ tests.',
    ],
    repos: ['https://github.com/Robwert0/AI-Career-Intelligence-Platform'],
  },
  {
    slug: 'jarvis',
    name: 'Jarvis',
    tagline: 'Voice-controlled AI assistant for the desktop',
    category: 'featured',
    context: 'Personal project',
    period: 'May 2026 – Jul 2026',
    purpose:
      "A personal assistant inspired by Iron Man's Jarvis: talk or type to it and it opens apps, runs multi-app macros, searches the web, controls the system and remembers facts about you.",
    description:
      'An Electron + React desktop app backed by a FastAPI service running a Claude tool-use loop. Voice conversations run through an ElevenLabs agent, and text and voice share one set of tools that execute locally on the machine. Single-user and runs locally by design.',
    stack: [
      'Python',
      'FastAPI',
      'Claude API',
      'ElevenLabs',
      'TypeScript',
      'React',
      'Electron',
      'SQLite',
      'pytest',
      'GitHub Actions',
    ],
    highlights: [
      'Full voice loop (speech-to-text → LLM → text-to-speech) with turn-taking and barge-in, plus a headless voice mode with a Porcupine wake word.',
      'Six tools shared by the text and voice paths: fuzzy app launching, macros, cooperative cancellation of in-flight actions, long-term memory, web search, and volume/media/lock control from WSL to Windows.',
      'Memories persisted in SQLite and injected into every text chat and voice session.',
      'HTTP chat endpoint with multi-turn history, a macro management API, and a pytest suite running in CI.',
    ],
    repos: ['https://github.com/Robwert0/jarvis'],
  },
  {
    slug: 'price-comparator',
    name: 'Price Comparator',
    tagline: 'Grocery price comparison across Romanian retailers',
    category: 'featured',
    context: 'Internship application coding challenge',
    period: 'May 2025',
    purpose:
      'Help shoppers spend less: compare grocery prices across Lidl, Kaufland and Profi, build the cheapest basket, and get told when a product drops to a target price.',
    description:
      'A Spring Boot REST backend that loads retailer price and discount lists from CSV files and exposes endpoints for baskets, discounts, price history, alerts and recommendations. Built as the take-home challenge for an internship application.',
    stack: ['Java', 'Spring Boot', 'REST APIs', 'OpenCSV', 'Spring Mail', 'Lombok', 'Maven'],
    highlights: [
      'Basket optimizer that splits a shopping list across stores to find the cheapest combination for the day.',
      'Discount tracking, including newly added discounts, and price history per product and store.',
      'Price alerts checked by a scheduled job and delivered by email.',
      'Recommendations by unit value (price per kg or litre), so different package sizes compare fairly.',
    ],
    repos: ['https://github.com/Robwert0/Price_comparator'],
  },
  {
    slug: 'face-recognition',
    name: 'Face Recognition Attendance',
    tagline: 'Real-time webcam face recognition that logs who is present',
    category: 'featured',
    context: 'University project, BSc Robotics, Transilvania University of Brasov',
    period: 'Dec 2024 – 2025',
    purpose:
      "Take attendance automatically: recognize registered people from a live webcam feed and log each person's presence with a time and confidence score.",
    description:
      'A Python pipeline covering the whole workflow: capture labelled face images from the webcam, train a classifier on them, then recognize faces live. MediaPipe finds and crops faces, a MobileNetV2 model fine-tuned with transfer learning identifies them, and a menu-driven entry point ties the stages together.',
    stack: [
      'Python',
      'TensorFlow / Keras',
      'MobileNetV2',
      'MediaPipe',
      'OpenCV',
      'filterpy',
      'PostgreSQL',
    ],
    highlights: [
      'Data collection that detects the face in each webcam frame with MediaPipe and saves labelled crops per person.',
      'Two-stage transfer learning on MobileNetV2: train a new head on frozen features, then fine-tune at a low learning rate with early stopping.',
      'Kalman filter to stabilize bounding boxes and exponential moving average to smooth confidence scores between frames.',
      'Presence log with name, timestamp and confidence for each recognized person.',
    ],
    repos: ['https://github.com/Robwert0/Face-Recognition-with-CNN-and-MediaPipe'],
  },
  {
    slug: 'employee-data-validator',
    name: 'Employee Data Validator',
    tagline: 'Validating and storing employee records with Pydantic and PostgreSQL',
    category: 'internship',
    context: 'Software Developer internship, BearingPoint',
    period: 'Jun 2024 – Aug 2024',
    purpose:
      'Make sure employee records are correct before anyone relies on them: reject malformed data, prevent duplicates, and export clean records for downstream analysis.',
    description:
      'A Python application that reads employee data from CSV, validates every field against strict rules with Pydantic models, and stores the result in PostgreSQL. It started with smaller Pydantic modelling exercises and grew into the full validator.',
    stack: ['Python', 'Pydantic', 'PostgreSQL', 'psycopg2', 'CSV'],
    highlights: [
      'Custom validators for email format, Romanian personal numeric code (CNP) structure and its consistency with gender, European countries and counties, and spoken and programming languages.',
      'Duplicate prevention on employee ID when appending validated records.',
      'Table creation and insert/update/delete/query scripts for PostgreSQL, driven by a column configuration.',
      'Location fields restructured into JSON for storage and export.',
    ],
    repos: ['https://github.com/Robwert0/Summer_Practice'],
  },
  {
    slug: 'websocket-chat',
    name: 'Websocket Chat',
    tagline: 'Real-time one-to-one chat over WebSockets',
    category: 'learning',
    context: 'Built by following a tutorial, to learn WebSockets and STOMP',
    period: 'Jul 2025',
    purpose:
      'Let users see who is online and message each other privately in real time, without refreshing the page.',
    description:
      'A Spring Boot backend using STOMP over WebSockets, with MongoDB for users, chat rooms and message history, and a plain JavaScript frontend using SockJS and Stomp.js. MongoDB runs in Docker Compose.',
    stack: [
      'Java',
      'Spring Boot',
      'Spring WebSocket',
      'STOMP',
      'MongoDB',
      'Docker Compose',
      'JavaScript',
    ],
    highlights: [
      'Live user presence that updates as users connect and disconnect.',
      'Private one-to-one conversations with chat history loaded when a conversation opens.',
      'Messages delivered instantly through STOMP subscriptions.',
    ],
    repos: ['https://github.com/Robwert0/Websocket_Chat'],
  },
  {
    slug: 'chess',
    name: 'Chess',
    tagline: 'A chess board built with pygame',
    category: 'learning',
    context: 'Personal practice',
    period: 'Apr 2024',
    purpose: 'Build a playable chess game in Python as practice with game loops and rendering.',
    description:
      'A pygame application that draws the board and all pieces from image assets. Move logic was started but not finished.',
    stack: ['Python', 'pygame'],
    highlights: ['Board and piece rendering with pygame from image assets.'],
    repos: ['https://github.com/Robwert0/ChessGame'],
  },
  {
    slug: 'cpp-mini-games',
    name: 'C++ Mini Programs',
    tagline: 'Sudoku solver, tic-tac-toe and a credit card validator',
    category: 'learning',
    context: 'Personal practice',
    period: 'Mar 2024',
    purpose: 'Practise C++ fundamentals through small, self-contained programs.',
    description:
      'Three console programs: a backtracking Sudoku solver, a two-player tic-tac-toe game, and a credit card number validator. The repository is private.',
    stack: ['C++'],
    highlights: [
      'Sudoku solved by backtracking with row, column and box safety checks.',
      'Tic-tac-toe with board drawing and win detection.',
      'Credit card numbers validated with the Luhn algorithm.',
    ],
    repos: [],
  },
  {
    slug: 'java-oop-exercises',
    name: 'Java OOP Exercises',
    tagline: 'Composition and inheritance exercises in Java',
    category: 'learning',
    context: 'Udemy Java course',
    period: 'Jun 2023',
    purpose: 'Learn object-oriented design in Java by modelling small domains.',
    description:
      'Two course exercises: a smart kitchen modelled with composition, and an employee hierarchy (worker, salaried and hourly employees) modelled with inheritance.',
    stack: ['Java', 'OOP'],
    highlights: [
      'Composition: a kitchen object that owns and coordinates its appliances.',
      'Inheritance: an employee class hierarchy with specialized pay behaviour.',
    ],
    repos: ['https://github.com/Robwert0/Composition', 'https://github.com/Robwert0/Inheritance'],
  },
  {
    slug: 'python-bootcamp',
    name: 'Python 3 Bootcamp',
    tagline: 'Course notebooks from the Complete Python 3 Bootcamp',
    category: 'learning',
    context: 'Udemy Python course (fork of the course repository)',
    period: 'Oct 2023',
    purpose: 'Learn Python from the ground up by working through the course material.',
    description:
      "A fork of the course's Jupyter notebooks, used while learning Python basics through object-oriented programming.",
    stack: ['Python', 'Jupyter'],
    highlights: ['Worked through the course notebooks and exercises.'],
    repos: ['https://github.com/Robwert0/Complete-Python-3-Bootcamp'],
  },
  {
    slug: 'git-demo',
    name: 'Git Demo',
    tagline: 'A small repository for practising Git',
    category: 'learning',
    context: 'Git practice',
    period: 'Nov 2025',
    purpose: 'Practise the basic Git workflow: commits, history and pushing to GitHub.',
    description: 'A throwaway repository with a text file edited over a few commits.',
    stack: ['Git', 'GitHub'],
    highlights: ['Commits, history and remotes practised on a single file.'],
    repos: ['https://github.com/Robwert0/git-demo'],
  },
]

export function getProject(slug: string): Project | undefined {
  return projects.find((project) => project.slug === slug)
}
