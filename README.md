\# PayrollGuard



\*\*Payroll Validation and Exception Management System\*\*



PayrollGuard is a payroll validation application designed to identify payroll data issues before payroll export. It processes employee, attendance, leave, allowance, and deduction records, applies validation rules, tracks exceptions, and checks payroll reconciliation.



The project uses synthetic payroll data and provides a FastAPI backend with a React dashboard.



\## Key Features



\- Synthetic payroll data generation with reproducible seed configuration.

\- Employee, attendance, leave, allowance, and deduction management.

\- Payroll calculation using approved input records.

\- Validation for missing employee details, duplicate entries, excess working hours, and unapproved time.

\- Exception management and resolution tracking.

\- Approval and rejection of pending time entries.

\- Audit history for tracked actions.

\- Payroll reconciliation.

\- CSV payroll export with validation checks.



\## Technology Stack



| Component | Technology |

|---|---|

| Backend | Python, FastAPI |

| Database | MySQL 8 |

| ORM | SQLAlchemy |

| Database driver | PyMySQL |

| Data generation | Faker, Pandas, NumPy |

| Frontend | React 19 |

| Build tool | Vite |

| UI charts | Recharts |

| Icons | Lucide React |



\## Project Structure



```text

payrollguard/

│

├── backend/

│   ├── app/

│   │   ├── api/

│   │   ├── models/

│   │   ├── services/

│   │   ├── database.py

│   │   ├── init\_db.py

│   │   └── main.py

│   │

│   ├── scripts/

│   │   └── generate\_data.py

│   │

│   ├── requirements.txt

│   └── .env.example

│

├── frontend/

│   ├── src/

│   ├── package.json

│   └── package-lock.json

│

├── data/

│   ├── generated/

│   └── ground\_truth/

│

├── docs/

│   ├── AI\_USAGE.md

│   ├── AI\_PROMPT\_HISTORY.md

│   ├── generation\_summary.json

│   ├── source\_manifest.json

│   └── schema\_snapshot.txt

│

└── README.md

```



\## Prerequisites



Install the following before running the project:



\- Python 3.10 or later

\- Node.js 22 or later

\- npm

\- MySQL Server 8.0 or later

\- Git



The project was developed using Python 3.10.11, Node.js 22.16.0, npm 10.9.2, and MySQL 8.0.22.



\## Installation and Setup



\### 1. Clone the repository



```bash

git clone https://github.com/likhithatalatam/payrollguard.git

cd payrollguard

```



\### 2. Create the MySQL database



Log in to MySQL:



```bash

mysql -u root -p

```



Create the database:



```sql

CREATE DATABASE payrollguard\_db;

EXIT;

```



\### 3. Configure the backend



Open the backend directory:



```bash

cd backend

```



Create a Python virtual environment:



```bash

python -m venv venv

```



Activate it on Windows PowerShell:



```powershell

.\\venv\\Scripts\\Activate.ps1

```



Install Python dependencies:



```bash

python -m pip install --upgrade pip

pip install -r requirements.txt

```



Create your local environment configuration:



```powershell

Copy-Item .env.example .env

```



Open `backend/.env` and replace `YOUR\_PASSWORD` with your local MySQL password:



```env

DATABASE\_URL=mysql+pymysql://root:YOUR\_PASSWORD@localhost:3306/payrollguard\_db

```



Do not commit your `.env` file or database credentials.



\### 4. Initialize database tables



Run this command from the `backend` directory:



```bash

python -m app.init\_db

```



This creates the database tables and seeds the validation rules.



\### 5. Generate synthetic payroll data



From the same `backend` directory, run:



```bash

python -m scripts.generate\_data

```



The generator uses a fixed random seed (`20261022`) to support reproducible data generation.



It generates:



\- 3,000 employees

\- 70,000 time entries

\- 15,000 allowance records

\- 15,000 deduction records

\- 4,500 leave records

\- 3 pay periods

\- 8 labelled ground-truth edge cases



The generator also produces CSV data files, a ground-truth file, a generation summary, and a source manifest.



\*\*Important:\*\* Data generation expects an empty database. Run it once after initializing a fresh database. It intentionally refuses to run when relevant database tables already contain records.



\### 6. Start the backend



From the `backend` directory:



```bash

uvicorn app.main:app --reload

```



Backend URL:



```text

http://127.0.0.1:8000

```



Interactive API documentation:



```text

http://127.0.0.1:8000/docs

```



\### 7. Install and start the frontend



Open a second terminal:



```bash

cd payrollguard/frontend

```



Install frontend dependencies:



```bash

npm ci

```



Start the development server:



```bash

npm run dev

```



Frontend URL:



```text

http://localhost:5173

```



The frontend communicates with the backend API at:



```text

http://127.0.0.1:8000/api

```



Keep both backend and frontend terminals running while using the application.



\## Running the Application



1\. Start MySQL.

2\. Start the FastAPI backend.

3\. Start the React frontend.

4\. Open `http://localhost:5173` in your browser.

5\. Use the dashboard to inspect payroll records and validation results.

6\. Review pending approvals and payroll exceptions.

7\. Check reconciliation results.

8\. Attempt payroll export after resolving issues that block export.



Payroll exports are restricted when payroll records require review or remain blocked.



\## Backend API



The backend exposes endpoints for:



| Endpoint | Purpose |

|---|---|

| `GET /api/dashboard` | Dashboard summary |

| `GET /api/periods` | List payroll periods |

| `GET /api/employees` | List employees |

| `POST /api/payroll/run/{pay\_period\_id}` | Process payroll |

| `GET /api/payroll/{pay\_period\_id}` | Retrieve payroll results |

| `GET /api/exceptions/{pay\_period\_id}` | Retrieve exceptions |

| `GET /api/reconciliation/{pay\_period\_id}` | Check payroll reconciliation |

| `GET /api/payroll/export/{pay\_period\_id}` | Export payroll CSV |

| `GET /api/time-entries/pending/{pay\_period\_id}` | List pending time entries |

| `POST /api/time-entries/{entry\_id}/decision` | Approve or reject a time entry |

| `POST /api/exceptions/{exception\_id}/resolve` | Resolve an exception |

| `GET /api/audit/{entity\_type}/{entity\_id}` | Retrieve audit history |



See the interactive Swagger documentation at `/docs` for request parameters and response formats.



\## Data and Documentation



\- `data/generated/` contains generated synthetic payroll CSV files.

\- `data/ground\_truth/` contains labelled validation edge cases.

\- `docs/generation\_summary.json` contains generation statistics.

\- `docs/source\_manifest.json` contains source data metadata and checksums.

\- `docs/AI\_USAGE.md` describes how AI assistance was used.

\- `docs/AI\_PROMPT\_HISTORY.md` documents the AI prompt history.



\## Limitations



\- This is a development prototype using synthetic data, not a production payroll platform.

\- The application has not undergone production security certification.

\- User identity and role information supplied to certain API actions are not backed by a complete authentication and authorization system.

\- Validation rules cover the implemented scenarios and do not guarantee detection of every possible payroll issue.

\- Generated data is intended for testing and demonstration, not actual payroll processing.



\## AI Usage Disclosure



ChatGPT was used as a development assistant for requirement analysis, implementation assistance, debugging, and documentation. Human setup, execution, database inspection, testing, and review were performed during development.



Further details are available in `docs/AI\_USAGE.md` and `docs/AI\_PROMPT\_HISTORY.md`.



\## Repository



GitHub: https://github.com/likhithatalatam/payrollguard

