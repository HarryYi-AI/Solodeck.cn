# SoloDeck.cn Deployment Guide

This guide uses:

- Private GitHub repo: `git@github.com:HarryYi-AI/Solodeck.cn.git`
- Frontend: Cloudflare Pages
- Backend: Render / Railway / VPS running FastAPI
- Domain: `solodeck.cn`
- Current DNS: `dns1.hichina.com`, `dns2.hichina.com`

## 1. Repository

Current remote should be:

```bash
git remote -v
```

Expected:

```text
origin  git@github.com:HarryYi-AI/Solodeck.cn.git
```

Before pushing, verify secrets are ignored:

```bash
git status --short --ignored
rg -n "api_key|OPENAI_API_KEY|AIPING|OPENAI_BASE_URL" . \
  --glob '!node_modules/**' \
  --glob '!dist/**' \
  --glob '!.git/**' \
  --glob '!data/solodeck_memory/**' \
  --glob '!data/solodeck_v3_memory/**' \
  --glob '!solo_creator_agent/data/audit_logs/**' \
  --glob '!solo_creator_agent/data/uploads/**'
```

## 2. Frontend on Cloudflare Pages

Create a new Cloudflare Pages project and connect the private GitHub repo.

Build settings:

```text
Framework preset: Vite
Build command: npm run build
Build output directory: dist
Root directory: /
```

Environment variable:

```text
SOLODECK_API_ORIGIN=https://api.solodeck.cn
```

The repository contains:

```text
functions/api/[[path]].js
```

This forwards Cloudflare Pages `/api/*` requests to `SOLODECK_API_ORIGIN`.

## 3. Backend API

Deploy the FastAPI backend separately.

Start command:

```bash
uvicorn solo_creator_agent.api_spa:app --host 0.0.0.0 --port $PORT
```

Build command:

```bash
pip install -r solo_creator_agent/requirements.txt
```

Required environment variables:

```text
OPENAI_BASE_URL=https://aiping.cn/api/v1
OPENAI_API_KEY=your-key
OPENAI_MODEL=Qwen3.5-Plus

OPENAI_API_KEY_BASIC=your-basic-key
OPENAI_MODEL_BASIC=Qwen3.5-Plus

OPENAI_API_KEY_ADVANCED=your-advanced-key
OPENAI_MODEL_ADVANCED=GLM-5-Turbo
```

Do not commit real keys.

## 4. DNS on HiChina / Aliyun DNS

Current DNS servers:

```text
dns1.hichina.com
dns2.hichina.com
```

Keep these DNS servers if you want to manage DNS inside Aliyun.

Recommended DNS records:

```text
Type: CNAME
Host: www
Value: <your-cloudflare-pages-project>.pages.dev
```

For the API:

```text
Type: CNAME
Host: api
Value: <your-backend-provider-domain>
```

If the backend runs on a VPS:

```text
Type: A
Host: api
Value: <server-public-ip>
```

For apex domain `solodeck.cn`, use one of these:

1. Add `@` CNAME if Aliyun DNS allows it for the domain.
2. Use URL forwarding from `solodeck.cn` to `www.solodeck.cn`.
3. Move DNS to Cloudflare nameservers and use Cloudflare CNAME flattening.

## 5. Cloudflare Pages Custom Domain

In Cloudflare Pages:

```text
Project -> Custom domains -> Set up a custom domain
```

Add:

```text
www.solodeck.cn
```

Then add the DNS CNAME in Aliyun DNS as prompted.

## 6. Verification

Frontend:

```bash
curl -I https://www.solodeck.cn
```

API:

```bash
curl https://www.solodeck.cn/api/health
```

Expected:

```json
{"ok":true,"service":"SoloDeck Skill API"}
```

V3 agent:

```bash
curl https://www.solodeck.cn/api/v3-agent \
  -H "Content-Type: application/json" \
  -d '{"task":"判断痛点标题是否提升咨询数，并生成下周验证计划"}'
```

## 7. Automatic Updates

After Cloudflare Pages is connected to GitHub:

```bash
git add .
git commit -m "update solodeck v3"
git push origin main
```

Cloudflare Pages will automatically:

```text
pull repo -> npm install -> npm run build -> publish dist
```

Backend providers such as Render or Railway can also auto-deploy after each push.
