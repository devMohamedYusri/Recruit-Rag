# RecruitRAG: AI-Powered Semantic Recruitment Tool
RecruitRAG is an intelligent recruitment assistant built to streamline the hiring process. By leveraging Retrieval-Augmented Generation (RAG), it allows recruiters to perform deep semantic searches across candidate resumes, extracting the most relevant talent using natural language queries instead of simple keyword matching.

## 🚀 Key Features

- **Semantic Search**: Go beyond keywords to find candidates based on context and experience.
- **Automated Summarization**: Quickly understand a candidate's profile with AI-generated summaries.
- **Intelligent Ranking**: Rank resumes based on job description relevance using vector embeddings.
- **WhatsApp Integration**: Potential for AI sales agents to interact with candidates or clients directly via WhatsApp.

## requirements
-python 3.11 or later


#### install python using miniconda
1) Download and install MiniConda from [here](https://docs.anaconda.com/free/miniconda/#quick-command-line-install)
2) Create a new environment using the following command:
```bash
$ conda create -n mini-rag python=3.8
```

3) Activate the environment:

```bash
$ conda activate mini-rag
```

## Installation the required packages

```bash
$ pip install r requirements.txt
```

## setup the environment variables
```bash
$ cp .env.example .env
```

set your environment variables in the `.env` file.

## Run the FASTAPI server

```bash
$ uvicorn main:app --reload --host 0.0.0.0 --port 5000
```