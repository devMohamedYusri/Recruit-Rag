<p align="center">
  <h1 align="center">🎯 RecruitRAG</h1>
  <p align="center">
    <strong>AI-Powered Semantic Recruitment Tool</strong>
  </p>
  <p align="center">
    Transform your hiring process with intelligent resume analysis powered by Retrieval-Augmented Generation (RAG)
  </p>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#api-reference">API Reference</a> •
  <a href="#license">License</a>
</p>

---

## 🌟 Overview

**RecruitRAG** is an intelligent recruitment assistant designed to streamline and enhance the hiring process. By leveraging Retrieval-Augmented Generation (RAG), it enables recruiters to perform deep semantic searches across candidate resumes, finding the most relevant talent using natural language queries instead of simple keyword matching.

> Say goodbye to manual resume screening. Let AI find your perfect candidates.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Semantic Search** | Go beyond keywords to find candidates based on context, skills, and experience |
| 📄 **Multi-Format Support** | Process resumes in PDF, DOCX, and TXT formats seamlessly |
| ⚡ **Smart Chunking** | Intelligent document processing with configurable chunk sizes for optimal retrieval |
| 📊 **Project Organization** | Organize candidates into separate projects for different job openings |
| 🗄️ **MongoDB Atlas** | Robust async document storage with MongoDB Atlas for scalability |
| 🔒 **JWT Authentication** | Secure API with token-based authentication and plan-based access control |
| 📈 **LangSmith Tracing** | Full observability of all LLM calls for debugging and optimization |
| 🐳 **Docker Ready** | One-command deployment with Docker |

---

## 🛠️ Tech Stack

<table>
<tr>
<td><strong>Backend</strong></td>
<td>FastAPI (Python 3.11+)</td>
</tr>
<tr>
<td><strong>AI/NLP</strong></td>
<td>LangChain, Google Gemini</td>
</tr>
<tr>
<td><strong>Database</strong></td>
<td>MongoDB Atlas (Async with PyMongo)</td>
</tr>
<tr>
<td><strong>Vector Store</strong></td>
<td>Qdrant Cloud</td>
</tr>
<tr>
<td><strong>Document Processing</strong></td>
<td>PyMuPDF4LLM, python-docx, Unstructured</td>
</tr>
<tr>
<td><strong>Hosting</strong></td>
<td>Render (Free Tier)</td>
</tr>
<tr>
<td><strong>Observability</strong></td>
<td>LangSmith</td>
</tr>
</table>

---

## 📋 Prerequisites

- **Python 3.11** or later
- **MongoDB Atlas** account (free tier works)
- **Qdrant Cloud** account (free tier works)
- **Google AI Studio** API key (for Gemini)

---

## 🚀 Getting Started

### Local Development

**1. Clone and setup environment**

```bash
git clone https://github.com/your-username/recruit_rag.git
cd recruit_rag

# Using Conda (Recommended)
conda create -n recruit python=3.11
conda activate recruit

# Or using venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment variables**

```bash
cp src/.env.example src/.env
```

Edit `src/.env` and configure your settings:

```env
MONGO_DB="mongodb+srv://<user>:<password>@<cluster>.mongodb.net/"
DB_NAME="recruit-rag-auth"
GEMINI_API_KEY="your_gemini_api_key"
JWT_SECRET_KEY="your_secure_random_secret"
QDRANT_URL="https://your-cluster.cloud.qdrant.io"
QDRANT_API_KEY="your_qdrant_api_key"
```

**4. Run the server**

```bash
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

---

## 🚢 Deployment

### Render (Recommended)

This project is configured for one-click deployment on [Render](https://render.com).

**1. Push to GitHub**

Ensure your code is pushed to a GitHub repository.

**2. Create a Web Service on Render**

- Go to [Render Dashboard](https://dashboard.render.com) → **New** → **Web Service**
- Connect your GitHub repository
- Render will auto-detect the `render.yaml` configuration

**3. Set Environment Variables**

In the Render dashboard, add these environment variables:

| Variable | Description |
|----------|-------------|
| `MONGO_DB` | MongoDB Atlas connection string |
| `DB_NAME` | Database name |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `JWT_SECRET_KEY` | Secure random string (min 32 chars) |
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |
| `GROQ_API_KEY` | Groq API key (for fallback) |
| `S3_ENDPOINT_URL` | S3-compatible storage endpoint |
| `S3_ACCESS_KEY_ID` | S3 access key |
| `S3_SECRET_ACCESS_KEY` | S3 secret key |
| `S3_BUCKET_NAME` | S3 bucket name |
| `LANGCHAIN_TRACING_V2` | `true` |
| `LANGCHAIN_API_KEY` | LangSmith API key |
| `LANGCHAIN_PROJECT` | LangSmith project name |
| `CORS_ORIGINS` | `["*"]` or your frontend domain |

**4. Deploy**

Render will automatically build and deploy. The service URL will be:
```
https://recruit-rag-api.onrender.com
```

**5. Keep-Alive (GitHub Actions)**

A GitHub Actions workflow (`.github/workflows/keep-alive.yml`) pings the health endpoint every 10 minutes to prevent the free instance from sleeping.

To set it up:
1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Add a secret: `RENDER_APP_URL` = `https://recruit-rag-api.onrender.com`

---

## 📡 API Reference

### Base URL
```
https://your-app.onrender.com/api/v1
```

### Endpoints

#### Upload Resumes
```http
POST /data/upload/{project_id}
```

Upload one or multiple resume files to a project.

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | `string` | Unique identifier for the recruitment project |
| `files` | `file[]` | Resume files (PDF, DOCX, TXT) |

**Response:**
```json
{
  "message": "Successfully uploaded 3 files",
  "files": [
    {"file_name": "resume_001.pdf", "file_id": "abc123..."}
  ],
  "status": "success"
}
```

---

#### Process Documents
```http
POST /data/process/{project_id}
```

Process uploaded resumes into searchable chunks.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_id` | `string` | - | Project identifier |
| `file_id` | `string` | `null` | Process specific file |
| `file_ids` | `string[]` | `null` | Process multiple files |
| `chunk_size` | `int` | `1000` | Size of text chunks |
| `chunk_overlap` | `int` | `200` | Overlap between chunks |
| `do_reset` | `bool` | `false` | Clear existing chunks before processing |

**Response:**
```json
{
  "file_count": 3,
  "total_chunks_count": 45,
  "errors_count": 0,
  "errors": [],
  "status": "success"
}
```

---

## 📁 Project Structure

```
recruit_rag/
├── .github/
│   └── workflows/
│       └── keep-alive.yml       # Cron to prevent Render sleep
├── src/
│   ├── main.py                  # FastAPI application entry point
│   ├── controllers/             # Business logic layer
│   │   ├── DataController.py
│   │   ├── ScreeningController.py
│   │   ├── VectorController.py
│   │   └── PlanGuardService.py
│   ├── models/                  # Data models & database schemas
│   ├── routes/                  # API route definitions
│   ├── stores/                  # LLM & Vector DB providers
│   ├── utils/                   # Configuration & utilities
│   └── assets/                  # Uploaded file storage
├── render.yaml                  # Render deployment config
├── Dockerfile                   # Docker deployment option
├── requirements.txt             # Python dependencies
├── .python-version              # Python version pin
└── LICENSE                      # MIT License
```

---

## 🔧 Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `APP_NAME` | Application name | `Recruit-Rag` |
| `APP_VERSION` | Application version | `0.9` |
| `MONGO_DB` | MongoDB connection string | - |
| `DB_NAME` | Database name | - |
| `GEMINI_API_KEY` | Google Gemini API key | - |
| `JWT_SECRET_KEY` | JWT signing secret | - |
| `LLM_CONCURRENCY_LIMIT` | Max parallel LLM calls | `5` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Rate limit per user | `60` |

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 👤 Author

**Mohamed Yusri**

---

<p align="center">
  <sub>Built with ❤️ for smarter recruiting</sub>
</p>