# AlignIQ - Project Documentation

## Overview
AI-powered document analysis platform for business requirement analysis. Users upload documents (PDF, DOCX, PPTX), get AI-generated recommendations on technologies, team structure, and project feasibility through multi-agent LLM orchestration.

## Tech Stack

### Frontend (`frontend/projectw/`)
- **Framework:** React 19 + TypeScript 5.7 + Vite 6.2
- **State:** Zustand + React Context
- **Styling:** Tailwind CSS 4.0
- **Data:** Axios + TanStack Query
- **PDF Export:** jsPDF + html2canvas

### Backend (`src/`)
- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL + SQLAlchemy ORM
- **Auth:** JWT + Google OAuth + Jira OAuth
- **LLM:** OpenAI (gpt-4o-mini) + LangChain + LangGraph
- **Vector DB:** Chroma (cloud)
- **Storage:** AWS S3

## Folder Structure
```
aligniq/
├── frontend/projectw/          # React frontend
│   ├── src/
│   │   ├── components/         # UI components
│   │   │   ├── chat/          # Chat interface
│   │   │   ├── integrations/  # Jira integration UI
│   │   │   ├── sidebar/       # Left sidebar
│   │   │   └── upload/        # Document upload
│   │   ├── context/           # AuthContext, DarkModeContext
│   │   ├── pages/             # Dashboard, Login, Register
│   │   ├── services/          # api.ts, chatService, conversationService
│   │   └── types/             # TypeScript definitions
├── src/                        # FastAPI backend
│   ├── agents/                 # LangGraph multi-agent workflow
│   │   ├── workflow_graph.py  # State machine orchestration
│   │   └── agentic_workflow.py # Agent implementations
│   ├── routers/
│   │   ├── authentication.py  # Auth endpoints
│   │   ├── services.py        # Upload, chat endpoints
│   │   └── third_party_integrations.py # Jira endpoints
│   ├── utils/
│   │   ├── chat_history.py    # DB chat operations
│   │   ├── integrations.py    # Jira API client
│   │   └── prompts.py         # LLM prompts
│   ├── vectordb/              # Chroma operations
│   ├── main.py                # FastAPI app entry
│   ├── models.py              # SQLAlchemy models
│   └── config.py              # Environment config
└── uploads/                    # Uploaded files directory
```

## Database Models (`src/models.py`)
- **User** - user_id, email, name, provider (Google/Jira/Local)
- **LoginDetails** - user credentials for local auth
- **UserDocuments** - document_id, user_id, document_path
- **ChatHistory** - chat_history_id, user_id, document_id, message (JSON), title
- **ReportVersions** - report_version_id, chat_history_id, report_content, summary_report
- **Session** - processing status tracking (created/uploaded/processing/completed/failed)

## API Endpoints

### Authentication (`/api/v1/auth/`)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/auth/login` | Google OAuth initiate |
| GET | `/auth/callback` | Google OAuth callback |
| GET | `/auth/jira/login` | Jira OAuth initiate |
| GET | `/auth/jira/callback` | Jira OAuth callback |
| POST | `/registration` | Register with email/password |
| POST | `/login` | Login with credentials |
| POST | `/validate_token` | Validate JWT token |

### Services (`/api/v1/`)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/upload/` | Upload documents, triggers processing |
| GET | `/task-status/{task_id}` | Check processing status |
| POST | `/chat` | Send message in conversation |
| GET | `/conversations` | Get all user conversations |
| GET | `/conversation/{chat_id}` | Get specific chat history |
| POST | `/chat-history` | Save chat message |
| GET | `/reports/{chat_id}` | Get generated report |

### Jira Integration (`/api/v1/jira/`)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/jira/get_issues` | Fetch user's Jira issues |
| GET | `/jira/get_single_issue/{issue_key}` | Get single issue details |
| GET | `/jira/download_attachments` | Download Jira attachment |

## Multi-Agent Workflow (`src/agents/`)
LangGraph state machine with 9 agents:
1. **Requirements Analyzer** - Parse and extract requirements
2. **Ambiguity Resolver** - Clarify unclear requirements
3. **Validator Agent** - Cross-validate requirements
4. **Midway Report Generator** - Interim analysis report
5. **Solution Architect** - Design technical solutions
6. **Critic Agent** - Feedback loop (max 3 iterations)
7. **Evidence Gatherer** - Collect supporting docs
8. **Feasibility Estimator** - Timeline/resource estimates
9. **BA Final Report Generator** - Final business analysis report

## User Flow
1. **Login** - Google OAuth / Email+Password / Jira OAuth
2. **Dashboard** - 3-panel layout (sidebar | chat | integrations)
3. **Upload** - Select documents → POST `/upload/`
4. **Processing** - Backend extracts text, runs agent pipeline
5. **Chat** - Response displayed, user can chat with POST `/chat`
6. **Conversations** - Left sidebar shows history, click to load
7. **Jira Integration** - Right panel shows issues, can pull attachments

## Key Files Reference
| File | Purpose |
|------|---------|
| `src/main.py:1` | FastAPI app initialization |
| `src/models.py:1` | Database schema definitions |
| `src/agents/workflow_graph.py:1` | Multi-agent orchestration |
| `src/routers/services.py:1` | Core API endpoints |
| `frontend/projectw/src/pages/Dashboard.tsx:1` | Main UI |
| `frontend/projectw/src/context/AuthContext.tsx:1` | Auth state |
| `frontend/projectw/src/services/api.ts:1` | API client config |

## Environment Variables (`.env`)
- **Database:** POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOSTNAME
- **Auth:** GOOGLE_CLIENT_ID, GOOGLE_CLIENT_TOKEN, SECRET_KEY_J, ALGORITHM
- **Jira:** JIRA_CLIENT_ID, JIRA_CLIENT_SECRET, JIRA_REDIRECT_URI
- **LLM:** OPENAI_CHATGPT
- **Storage:** S3_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
- **Vector DB:** CHROMA_API_KEY, CHROME_TENANT, CHROMA_DATABASE

## Frontend Components Structure
```
Dashboard (main page)
├── Sidebar (left)
│   ├── Logo/Header
│   ├── NewChatButton
│   ├── ConversationList (grouped: today/yesterday/older)
│   └── ProfileMenu
├── ChatArea (center)
│   ├── DocumentUpload (initial state)
│   └── ChatInterface (after upload)
│       ├── MessageList
│       └── ChatInput
└── RightSidebar (integrations - hidden by default)
    ├── IntegrationTabs (Jira/GitHub/Azure)
    └── JiraTab → JiraIssueDetail
```

## Request/Response Models (`src/p_model_type.py`)
- `UploadDoc` - expected_time, list_of_developers
- `Registration_login_password` - email, given_name, family_name, password
- `login_details` - email_address, password
- `MessageContent` - role, content, timestamp, selected
- `ChatHistoryDetails` - chat_history_id, user_id, document_id, message[], title
