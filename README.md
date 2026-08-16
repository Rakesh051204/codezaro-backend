# CodeZaro — AI Code Review Frontend

React frontend for **CodeZaro**, an AI-powered code review platform with tiered LLM-based static analysis.

> Backend: [codezaro-backend](https://github.com/Rakesh051204/codezaro-backend)

## What it does

CodeZaro's UI lets users submit code for AI-powered review, choose their analysis tier, and manage their own API keys (BYOK) — all through a clean, developer-focused interface.

- **Code submission & review UI** — paste or upload code, get structured AI feedback
- **Tiered analysis selector** — choose review depth
- **BYOK key management** — securely add and manage personal API keys
- **JWT-authenticated sessions**

## Tech Stack

| Layer | Tech |
|---|---|
| Framework | React |
| Auth | JWT |
| Deployment | Vercel |

## Running Locally

```bash
npm install
npm start
```

Requires [codezaro-backend](https://github.com/Rakesh051204/codezaro-backend) running locally or deployed, with the API URL configured in `.env`.

---

Built by [Rakesh Palani](https://github.com/Rakesh051204) — part of a broader portfolio of AI-powered products.
