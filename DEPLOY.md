---
noteId: "1beb7760ded611f183e21f0fdf7dd47a"
tags: []

---

# Deploying to Render

This application uses Flask with a MySQL-compatible database. Render's web
service runs the Flask application; provide a managed or external MySQL
database separately.

## 1. Create the web service

1. Push this repository to a Git provider connected to Render.
2. In Render, create a **Web Service** for the repository.
3. Use the repository root as the root directory and select the supported
   Python runtime for the app.
4. Set the build command to:

   ```text
   pip install -r requirements.txt
   ```

5. Set the start command to:

   ```text
   gunicorn wsgi:app
   ```

## 2. Configure environment variables

Add these values in the Render service's **Environment** settings:

| Variable | Required | Value |
| --- | --- | --- |
| `SECRET_KEY` | Yes | A unique, long random secret; do not reuse the development value. |
| `DATABASE_URL` | Yes | A MySQL connection URL, preferably `mysql+pymysql://user:password@host:port/database`. URL-encode special characters in credentials. |
| `ADMIN_PASSWORD` | For initial seed | A strong password for the initial `admin` account. |
| `DB_SSL_CA` | Optional | Path to the database provider's CA certificate file, if it requires CA-based TLS verification. |
| `REDIS_URL` | Optional | Redis connection URL. The app can use its in-memory cache if Redis is unavailable. |

Use Render Secret Files for a database CA certificate, then set `DB_SSL_CA` to
that file's path. Never put secrets in source control or in `DEPLOY.md`.

## 3. Apply the database schema

Once the service has the production `SECRET_KEY` and `DATABASE_URL` values,
open the service shell (or run the equivalent command in a deployment job) and
apply migrations:

```text
flask --app wsgi db upgrade
```

The database URL must point to the intended production database, not the test or
development database.

## 4. Seed production access and settings

Set `ADMIN_PASSWORD` in the service environment before running the production
seed command:

```text
python -m app.seeds.seed_production
```

This creates roles and their permission grants, generic initial settings, and
the `admin` account only. It does not create menu, customer, order, inventory,
or other sample records. The seed can be run again safely; it applies the
current `ADMIN_PASSWORD` to the admin account, so set the desired password
before each seed run. After initial setup, remove `ADMIN_PASSWORD` from the
service environment if it is no longer needed.

## Runtime storage

The app does not persist runtime uploads, reports, or logs to the local
filesystem. Report CSV downloads are generated in memory. Keep production
uploads in external object storage if that feature is added later; Render's
service filesystem should not be used for persistent application data.
