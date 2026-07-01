---
title: MKT Automation Job Summarizer
emoji: 💼
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# MKT Automation Job Summarizer

FastAPI application that reads a public job URL and produces a structured summary.

## AI configuration

The application calls the Gemini API and does not download or run a local Hugging Face model. Copy `.env.example` to `.env` for local development, then set a valid `GEMINI_API_KEY`. The `.env` file is ignored by Git and Docker.

`GEMINI_MODEL` is optional. The default is `gemini-3.5-flash`.

## Vercel deployment

The repository includes `index.py` as the Vercel FastAPI entrypoint. Import the Git repository in Vercel with the project root as the Root Directory; no custom Build Command or Output Directory is required.

In **Project Settings > Environment Variables**, configure these values for Production and Preview:

- `GEMINI_API_KEY` (required, mark it sensitive)
- `GEMINI_MODEL` (optional, defaults to `gemini-3.5-flash`)

Git-based CI/CD works as follows:

- Every push and pull request runs the GitHub Actions test suite.
- Pushes to non-production branches create Vercel Preview deployments.
- Merges or pushes to the Vercel Production Branch (`master` for this repository) create Production deployments.

The GitHub repository should protect `master` and require the `test` check before merging. Vercel handles deployment directly through its Git integration, so no Vercel token is stored in GitHub Actions.

## Optional Docker deployment

The Docker configuration remains available for other container hosts. It exposes port `7860` and does not need PyTorch, Transformers, a GPU, or local model storage.

### Manual first deployment

1. Create a public Docker Space at <https://huggingface.co/new-space>.
2. Select **Docker** and **CPU Basic (Free)**.
3. In the Space, open **Settings > Variables and secrets** and add `GEMINI_API_KEY` as a secret. Optionally add `GEMINI_MODEL` as a variable.
4. Create a Hugging Face write token at <https://huggingface.co/settings/tokens>.
5. Add the Space as a Git remote and push:

```powershell
git remote add hf https://huggingface.co/spaces/HF_USERNAME/SPACE_NAME
git push hf master:main
```

When Git asks for credentials, use the Hugging Face username and the write token as the password. Never commit the token.

### Development workflow

- Develop and push unfinished work to `develop`.
- Open a pull request from `develop` to `master`.
- Merge only after tests pass.
- Vercel deploys `develop` as Preview and `master` as Production.

Free CPU Spaces sleep after inactivity. The first visitor after sleep must wait for the container to start, but there is no local model-loading delay.
