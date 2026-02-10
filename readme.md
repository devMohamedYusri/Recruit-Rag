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
| 🗄️ **MongoDB Storage** | Robust async document storage with MongoDB for scalability |
| 🐳 **Docker Ready** | One-command deployment with Docker Compose |

---

## 🛠️ Tech Stack

<table>
<tr>
<td><strong>Backend</strong></td>
<td>FastAPI (Python 3.11+)</td>
</tr>
<tr>
<td><strong>AI/NLP</strong></td>
<td>LangChain, LangChain Community Loaders</td>
</tr>
<tr>
<td><strong>Database</strong></td>
<td>MongoDB (Async with Motor)</td>
</tr>
<tr>
<td><strong>Document Processing</strong></td>
<td>PyMuPDF4LLM, Docx2txt, RecursiveCharacterTextSplitter</td>
</tr>
<tr>
<td><strong>Infrastructure</strong></td>
<td>Docker, Docker Compose</td>
</tr>
</table>

---

## 📋 Prerequisites

- **Python 3.11** or later
- **MongoDB** (local or containerized)
- **Docker & Docker Compose** (optional, for containerized deployment)

---

## 🚀 Getting Started

### Option 1: Using Conda (Recommended)

**1. Install Miniconda**

Download and install from the [official Miniconda page](https://docs.anaconda.com/free/miniconda/#quick-command-line-install).

**2. Create and activate environment**

```bash
conda create -n recruit-rag python=3.11
conda activate recruit-rag
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

```bash
cp src/.env.example src/.env
```

Edit `src/.env` and configure your settings:

```env
APP_NAME="Recruit-Rag"
APP_VERSION="0.1"
MONGO_DB="mongodb://localhost:27017"
DB_NAME="recruit_rag"
FILE_MAX_SIZE_MB=5
FILE_ALLOWED_TYPES=["text/plain","application/pdf"]
```

**5. Start MongoDB** (using Docker)

```bash
cd docker
cp .env.example .env
# Edit .env with your MongoDB credentials
docker-compose up -d
```

**6. Run the server**

```bash
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

### Option 2: Using pip directly

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp src/.env.example src/.env
# Edit src/.env with your configuration

# Run server
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

---

## 📡 API Reference

### Base URL
```
http://localhost:5000/api/v1
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
├── src/
│   ├── main.py              # FastAPI application entry point
│   ├── controllers/         # Business logic layer
│   │   ├── DataController.py     # File upload & validation
│   │   ├── ProcessController.py  # Document processing & chunking
│   │   └── ProjectController.py  # Project management
│   ├── models/              # Data models & database schemas
│   │   ├── AssetModel.py         # File asset management
│   │   ├── ChunkModel.py         # Document chunks
│   │   └── ProjectModel.py       # Project entities
│   ├── routes/              # API route definitions
│   │   ├── base.py               # Health check & base routes
│   │   └── data.py               # Data upload & processing routes
│   ├── utils/               # Utility functions & configuration
│   └── assets/              # Uploaded file storage
├── docker/
│   ├── docker-compose.yaml  # MongoDB container configuration
│   └── .env.example         # Docker environment template
├── requirements.txt         # Python dependencies
└── LICENSE                  # MIT License
```

---

## 🔧 Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `APP_NAME` | Application name | `Recruit-Rag` |
| `APP_VERSION` | Application version | `0.1` |
| `MONGO_DB` | MongoDB connection string | - |
| `DB_NAME` | Database name | - |
| `FILE_MAX_SIZE_MB` | Maximum file size in MB | `5` |
| `FILE_ALLOWED_TYPES` | Allowed MIME types | `["text/plain", "application/pdf"]` |

---

## 🗺️ Roadmap

- [ ] Vector embeddings for semantic search
- [ ] AI-powered candidate ranking and scoring
- [ ] Automated resume summarization
- [ ] WhatsApp integration for candidate communication
- [ ] Advanced filtering and search UI
- [ ] Batch processing with Celery workers

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