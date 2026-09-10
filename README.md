# Uchko - Adaptive Learning Platform

Uchko is a Django-based adaptive learning platform developed as a university project for the Seminar in Artificial Intelligence course.

The platform presents mathematics problems from the FoundationalASSIST dataset, estimates a student's knowledge state, predicts the probability of answering a problem successfully, and adaptively selects the next learning item.

## Main features

- Student and professor accounts with role-based access
- Course enrollment and student management
- Adaptive selection of mathematics problems
- Support for numeric and single-choice questions
- Persistent learning attempts and sessions
- Per-skill mastery tracking
- Student progress and curriculum views
- Professor dashboards for enrolled students
- Sanitized rendering of imported HTML and MathML content
- XGBoost success prediction
- Bayesian Knowledge Tracing mastery updates

## Adaptive learning architecture

Uchko combines two complementary models:

1. **XGBoost** predicts the probability that a student will answer a candidate problem successfully. It uses problem metadata together with leakage-safe sequential features derived from the student's previous attempts.

2. **Bayesian Knowledge Tracing (BKT)** maintains a mastery probability for each curriculum skill and updates it after every independent attempt.

The adaptive service combines predicted success, current mastery, answer support, and recent practice history to select an appropriate next problem.

## Model results

Models were evaluated using student-level train, validation, and test splits.

| Model | Split | ROC AUC | Accuracy | Log loss |
| --- | --- | ---: | ---: | ---: |
| History baseline | Test | 0.6929 | 0.6728 | 0.6075 |
| BKT | Test | 0.6850 | 0.6772 | 0.6105 |
| XGBoost | Validation | 0.8087 | 0.7421 | 0.5113 |
| XGBoost | Test | **0.8122** | **0.7440** | **0.5061** |

The trained artifacts and evaluation reports are stored in:

```text
ml/artifacts/
ml/reports/
```

Training and preprocessing scripts are stored in:

```text
ml/scripts/
```

## Project structure

```text
accounts/           Authentication, user roles and registration
courses/            Courses, enrollments, learning data and import commands
learning/           Adaptive service and student-facing learning views
ml/                 Feature building, inference, artifacts and training scripts
uchko_project/      Django configuration and root URL configuration
docs/               Additional project documentation
manage.py           Django management entry point
requirements.txt    Python dependencies
```

## Local setup

Create and activate a virtual environment.

### Windows

```cmd
python -m venv .venv
.venv\Scripts\activate
```

### Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies and initialize the database:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
```

Create the demo course and accounts:

```bash
python manage.py seed_demo
```

Start the development server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## Demo accounts

The `seed_demo` command creates the following local demonstration accounts:

| Role | Username | Password |
| --- | --- | --- |
| Professor | `professor_demo` | `UchkoDemo2026!` |
| Student | `student_demo_1` | `UchkoDemo2026!` |
| Student | `student_demo_2` | `UchkoDemo2026!` |

These credentials are intended only for local demonstration data.

## Importing FoundationalASSIST content

Download the dataset from:

<https://huggingface.co/datasets/ASSISTments/FoundationalASSIST>

Only `Problems.csv` and `Skills.csv` are required by the Django application.

Import them into an existing course:

```bash
python manage.py import_foundational_assist \
  --course-code UCHKO-DEMO \
  --problems /absolute/path/to/Problems.csv \
  --skills /absolute/path/to/Skills.csv
```

On Windows, the command can be written on one line:

```cmd
python manage.py import_foundational_assist --course-code UCHKO-DEMO --problems "C:\path\to\Problems.csv" --skills "C:\path\to\Skills.csv"
```

The command is idempotent: running it again updates existing learning items instead of creating duplicates.

## Data privacy

Protected student interaction records from FoundationalASSIST are not imported into the Django application and are not stored in this Git repository.

The interaction data was processed only in the access-controlled university environment for model training and aggregate evaluation. The application imports only problem content and curriculum skill metadata.

Users of the dataset must follow its license and access requirements.

## Security

Imported problem bodies and answer options may contain HTML and MathML. Before rendering, Uchko sanitizes this content using an explicit allowlist of:

- supported HTML and MathML tags,
- safe attributes,
- safe CSS properties,
- approved image hosts and URL schemes.

Scripts, event handlers, unsafe image sources, and dangerous layout properties are removed.

## Running checks and tests

```bash
python manage.py check
python manage.py test
```

The test suite covers course authorization and imported-content sanitization.

## Development configuration

Local configuration can be overridden using environment variables:

```text
SECRET_KEY
DEBUG
ALLOWED_HOSTS
```

The default settings are intended for local development only and must not be used for a public production deployment.