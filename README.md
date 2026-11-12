# Restaurant Management System

A Flask application for restaurant operations, including menu and inventory management, point of sale, orders, tables and reservations, staff, billing, notifications, and management reports.

## Requirements

- Python 3.10 or newer
- XAMPP with MySQL/MariaDB, or another compatible MySQL server
- Python dependencies from `requirements.txt`
- `pytest` to run the test suite

## Windows setup with XAMPP

1. Install and start **MySQL** from the XAMPP Control Panel.
2. Open phpMyAdmin (`http://localhost/phpmyadmin`) and create the application database `restaurant_db`. Create a separate `restaurant_test_db` for tests.
3. From the project directory, create and activate a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   pip install pytest
   ```

4. Create a `.env` file in the project root and set database URLs for your local MySQL account. Replace the example username/password as appropriate:

   ```dotenv
   SECRET_KEY=replace-with-a-long-random-secret
   DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/restaurant_db
   TEST_DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/restaurant_test_db
   REDIS_URL=redis://localhost:6379/0
   ```

   For an XAMPP installation with an empty root password, use `root:` before the `@` in each URL. Keep `TEST_DATABASE_URL` pointed at a disposable test database: the test fixtures drop and recreate its tables.

## Database initialization

Apply database migrations:

```powershell
flask --app run.py db upgrade
```

Seed initial roles, users, and sample application records:

```powershell
python -m app.seeds.seed_data
```

## Run the application

```powershell
python run.py
```

Open `http://127.0.0.1:5000`.

## Tests

Set `TEST_DATABASE_URL` to `restaurant_test_db` before running tests. In PowerShell, for example:

```powershell
$env:TEST_DATABASE_URL = "mysql+pymysql://root:YOUR_PASSWORD@127.0.0.1:3306/restaurant_test_db"
pytest -q
```

Never point the test URL at the development or production database.

## Default administrator login

The seed data creates this administrator account:

- **Username:** `admin`
- **Password:** `Admin@123`

Change the seeded password before using the application outside local development.

## Roles

- **Admin** — full administrative access
- **Manager** — restaurant operations, staff, customers, and management features
- **Waiter** — table service and point-of-sale ordering
- **Kitchen** — kitchen display and order progress
- **Cashier** — checkout and billing
