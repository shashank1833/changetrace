# ChangeTrace Production Deployment Guide

This guide covers advanced production deployment, environment variables, GitHub App integration, and SSL setup.

---

## 1. Environment Configuration

Copy the example file and customize your production values:

```bash
cp .env.example .env.production
```

### Production Keys

| Key | Description | Example |
| :--- | :--- | :--- |
| `CHANGETRACE_ENVIRONMENT` | Set to `production` to enforce security checks | `production` |
| `CHANGETRACE_AUTH_MODE` | Authentication mode (`oauth` or `development`) | `oauth` |
| `CHANGETRACE_SESSION_SECRET` | 64-char random hex key for signing cookies | Generated via `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CHANGETRACE_SESSION_COOKIE_SECURE` | Force secure HTTPS cookie transmission | `true` |
| `CHANGETRACE_ALLOWED_ORIGINS` | Web frontend domain(s) allowed by CORS | `https://changetrace.yourdomain.com` |
| `CHANGETRACE_WEB_URL` | Public web frontend URL | `https://changetrace.yourdomain.com` |
| `CHANGETRACE_GITHUB_CLIENT_ID` | GitHub OAuth App Client ID | From GitHub Developer Settings |
| `CHANGETRACE_GITHUB_CLIENT_SECRET` | GitHub OAuth App Client Secret | From GitHub Developer Settings |
| `CHANGETRACE_GITHUB_CALLBACK_URL` | OAuth redirect callback endpoint | `https://changetrace.yourdomain.com/api/v1/auth/github/callback` |
| `POSTGRES_PASSWORD` | Strong PostgreSQL database password | Cryptographically random string |
| `CHANGETRACE_REDIS_PASSWORD` | Strong Redis instance password | Cryptographically random string |

---

## 2. Launching with Production Docker Compose

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

---

## 3. Free Domain & SSL Options (No Domain Required)

- **Public VPS (AWS, DigitalOcean, Hetzner):** Use **`sslip.io`** (e.g., `https://<your-ip>.sslip.io`) with Let's Encrypt Certbot.
- **Local / Home Server:** Use **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8080`) for instant free HTTPS.
- **Local Testing:** GitHub OAuth officially supports `http://localhost:8080` without requiring any domain.
