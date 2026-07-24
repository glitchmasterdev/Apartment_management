# Hosting Instructions – Nairobi Rental Management Platform

This guide outlines how to deploy the platform to production using **Supabase** (Database, Auth, and RLS) and **Vercel** (Frontend & FastAPI Serverless Backend).

---

## 1. Setup Supabase (Database & Auth)

1. **Create a Supabase Project**:
   - Go to [Supabase](https://supabase.com/) and create a new project.
   - Choose your database region and set a secure database password.

2. **Execute Database Schema**:
   - Go to the **SQL Editor** tab in your Supabase project dashboard.
   - Click **New Query**, paste the contents of [supabase_schema.sql](supabase_schema.sql), and click **Run**.
   - This sets up all tables, seeding values, and Row Level Security (RLS) policies.

3. **Get API Credentials**:
   - Go to **Project Settings** → **API**.
   - Copy the following values:
     - `Project URL`
     - `anon public` key
     - `service_role` key (keep this secret)

## 2. Configure SMTP & Resend Email Services

To send receipts, rejection reasons, welcome letters, and real password reset emails:
1. **SMTP Configuration (For system notifications)**:
   - Go to **Project Settings** → **Auth** → **SMTP** in Supabase.
   - Enable the **SMTP Provider** and fill in your details (e.g. Gmail SMTP).

2. **Resend Configuration (For custom transactional password resets)**:
   - Sign up for a free account at [Resend](https://resend.com/).
   - Obtain an API key from the **API Keys** tab.
   - You will use this key as the `RESEND_API_KEY` environment variable.

---

## 3. Setup Vercel Deployment

1. **Create a Vercel Project**:
   - Go to [Vercel](https://vercel.com/) and click **Add New** → **Project**.
   - Import your git repository containing this project.

2. **Configure Environment Variables**:
   - During the import setup, go to the **Environment Variables** section.
   - Add the following keys:
     ```env
     SUPABASE_URL=https://your-project-id.supabase.co
     SUPABASE_ANON_KEY=your-supabase-anon-public-key
     SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-secret-key

     RESEND_API_KEY=re_your_actual_resend_api_key
     APP_URL=https://your-app-domain.vercel.app

     SMTP_HOST=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USER=your-smtp-username@gmail.com
     SMTP_PASS=your-smtp-app-password
     SMTP_FROM_EMAIL=noreply@yourdomain.com
     ```

3. **Deploy**:
   - Click **Deploy**. Vercel will automatically read `vercel.json`, deploy the `public/` directory as static assets, and package the `api/` directory into Python FastAPI serverless functions.


---

## 4. Local Testing & Verification

For testing prior to connecting to a real Supabase instance:
- Run:
  ```powershell
  python -m uvicorn api.main:app --reload --port 8000
  ```
- If the `SUPABASE_URL` and keys are empty or default, the platform automatically runs in **Mock Database Mode**, storing data in volatile memory so you can preview, edit settings, approve tenants, and test PWA installations with zero database cost.
