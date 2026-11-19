# Convention POS

Django project for convention booths: anonymous customers browse/search goods, sellers
register booths (in pairs/groups) and submit goods lists, staff verify booths and goods,
and sellers run a POS (cart, checkout, history, void) for their approved booth.

## Setup (Windows / VS Code)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then put a random value in DJANGO_SECRET_KEY
python manage.py migrate
python manage.py createsuperuser   # becomes an admin with a Staff profile
python manage.py runserver
python manage.py test
```
`.env` is read automatically by `settings.py`. `DJANGO_DB=sqlite` needs no database server;
set `DJANGO_DB=postgres` and the `POSTGRES_*` values to use PostgreSQL.

**Quick demo data (local only):** set `DEMO_PASSWORD` in `.env`, then run
`python manage.py seed_demo` (add `--admin` to let the demo staff user open `/admin/`).
It creates fake staff, sellers, booths, goods and sales; log in as `staff.nok`, `mint.seller`
or `ploy.seller`. Instructions are at the top of `sales/management/commands/seed_demo.py`.

## Authentication rules (proposal 4.3.4)
- Public registration creates **sellers only**; staff accounts are created by staff at `/accounts/staff/new/`.
- Passwords: min 8 chars, upper + lower case + one of `!@#$%^&*()_+`, Django's common/numeric checks.
- Usernames: letters, numbers, `.` and `-` only.
- 5 failed logins for a username within 15 min -> locked for 15 min (20 per IP address).
- Sessions last 24 h; staff are logged out after 30 min idle. Log out is POST only.
- Logins, failures, lockouts, logouts, registrations, staff creation, password changes and
  denied access are written to `AuditLog` (read-only in the admin).

## Creating staff and lookup data
Open the admin (`/admin/`, configurable via `DJANGO_ADMIN_URL`):
1. Staff accounts: log in as staff and use **New staff account**, or in the admin add a user with **role = staff** and fill in the **Staff** inline.
2. Add **Fandoms** and **Merch types** (sellers pick from these when submitting goods).
3. Add **Blacklist** entries (by seller and/or bank account number).

## Use case -> URL
| Use case | Actor | URL |
|---|---|---|
| View / Search goods (name, fandom, type, booth) + recommendations | Customer (no login) | `/`, `/goods/<id>/` |
| Register user | Seller | `/accounts/register/` |
| Register staff | Staff only | `/accounts/staff/new/` |
| Edit user's information | Seller (own) / Staff (any seller) | `/accounts/profile/`, `/accounts/password/`, `/accounts/users/` |
| Log in / Log out | Seller, Staff | `/accounts/login/`, `/accounts/logout/` (POST) |
| Register booth (+ check blacklist) | Seller | `/booths/register/` |
| Edit booth's information | Seller | `/booths/<id>/edit/` |
| Submit goods list | Seller | `/sell/<booth_id>/goods/` |
| Verify booth / check blacklist | Staff | `/booths/review/` |
| Verify goods list | Staff | `/staff/booths/<booth_id>/goods/` |
| POS: cart + checkout (approved booth, approved goods only) | Seller (booth member) | `/pos/<booth_id>/` |
| Transaction history / detail | Seller (booth member) | `/pos/<booth_id>/transactions/` |
| Void transaction (restores stock, POST only) | Seller (booth member) | `/pos/<booth_id>/transactions/<id>/void/` |

A seller opening another seller's booth, goods list or POS gets **403** and an `Access denied` audit entry.
POS stock rules live in `sales/services.py`.
