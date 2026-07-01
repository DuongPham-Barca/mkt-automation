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

## Hugging Face deployment

Hugging Face Spaces is used only to host the FastAPI Docker application. The container exposes port `7860` and does not need PyTorch, Transformers, a GPU, or local model storage.

### Manual first deployment

1. Create a public Docker Space at <https://huggingface.co/new-space>.
2. Select **Docker**, **CPU Basic (Free)**, and use the same repository name configured in `HF_SPACE_ID` below.
3. In the Space, open **Settings > Variables and secrets** and add `GEMINI_API_KEY` as a secret. Optionally add `GEMINI_MODEL` as a variable.
4. Create a Hugging Face write token at <https://huggingface.co/settings/tokens>.
5. Add the Space as a Git remote and push:

```powershell
git remote add hf https://huggingface.co/spaces/HF_USERNAME/SPACE_NAME
git push hf master:main
```

When Git asks for credentials, use the Hugging Face username and the write token as the password. Never commit the token.

### Automatic deployment from GitHub

In the GitHub repository, open **Settings > Secrets and variables > Actions** and configure:

- Repository secret `HF_TOKEN`: a fine-grained Hugging Face token with write access to this Space.
- Repository variable `HF_SPACE_ID`: `HF_USERNAME/SPACE_NAME`.

Every push to `master` then runs the tests. If they pass, GitHub Actions force-syncs `master` to the Space's `main` branch, which rebuilds and restarts automatically.

### Development workflow

- Develop and push unfinished work to `develop`.
- Open a pull request from `develop` to `master`.
- Merge only after tests pass.
- Only `master` is deployed to the public demo.

Free CPU Spaces sleep after inactivity. The first visitor after sleep must wait for the container to start, but there is no local model-loading delay.
