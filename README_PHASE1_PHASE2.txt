SHIRE VILLAS AI REVENUE OS - PHASE 1 + PHASE 2

WHAT THIS PACKAGE FIXES
1. Fixes missing schema imports that can break app startup.
2. Adds TEAM_API_KEY protection to internal lead/dashboard/activity routes.
3. Removes insecure wildcard CORS defaults for production.
4. Requires SECRET_KEY and TEAM_API_KEY in production.
5. Separates anonymous website visits from actual CRM leads.
6. Meta "Lead" conversion is no longer fired merely on page view.
7. A real lead is created only after contact capture + qualification.
8. Adds input length/range validation.
9. Stops leaking Groq/provider exception messages to prospects.
10. Adds output escaping in the dashboard to reduce stored-XSS risk.

FILES TO ADD
- app/security.py

FILES TO REPLACE COMPLETELY
- app/config.py
- app/main.py
- app/models/lead.py
- app/schemas/lead.py
- app/routers/leads.py
- app/routers/activities.py
- app/routers/dashboard.py
- app/routers/ai.py
- app/services/ai_service.py
- frontend/index.html
- frontend/landing.html
- frontend/chatbot.html

RAILWAY ENVIRONMENT VARIABLES
ENV=production
TEAM_API_KEY=<make a long random private key>
SECRET_KEY=<make a different long random private key>
CORS_ORIGINS=https://YOUR-RAILWAY-DOMAIN.up.railway.app
DATABASE_URL=<Railway Postgres variable/reference>
GROQ_API_KEY=<optional>
GROQ_MODEL=llama-3.1-8b-instant
META_PIXEL_ID=<optional>

IMPORTANT DATABASE NOTE
This package uses SQLAlchemy create_all for now. Adding the new "visits"
table is safe because create_all creates missing tables. Existing leads
remain in the leads table.

However, the project still needs Alembic migrations before future
production schema changes. That is a Phase 1.5 improvement.

TEST AFTER DEPLOYMENT
1. /health should return version 2.0.0.
2. /app/landing.html should open.
3. Opening the landing page should increase Website Visits, not Real Leads.
4. /app/ should ask for Team API Key.
5. Enter TEAM_API_KEY.
6. Complete QBot with phone/email.
7. Real Leads should increase by one.
8. /leads/ without X-Team-Key should return 401.
9. /dashboard/ without X-Team-Key should return 401.
