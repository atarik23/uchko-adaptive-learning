# Uchko — Django Port

This is a Django port of the original Streamlit-based Uchko adaptive learning demo.
The core ML / domain logic in `uchko_core/` is unchanged; only the UI layer was rewritten.

## What changed

| Streamlit | Django |
| --- | --- |
| `app/streamlit_app.py` (single script) | `learning/views.py`, `learning/urls.py`, templates |
| `st.session_state` | `request.session` (DB-backed) |
| `st.cache_data` | module-level cache in `learning/services.py` |
| `st.tabs` | nav links between `practice/`, `progress/`, `curriculum/`, `settings/` |
| `st.button` / `st.form` | HTML forms posting to dedicated views |
| `st.dataframe` | rendered HTML tables |
| `st.pyplot` | server-rendered PNG at `/curriculum/graph.png` |
| `st.download_button` | `/export/session.csv` view |

The original event store (Parquet), user store (JSON), risk model
(`models/edm_risk_gbm/`) and BKT params (`models/bkt_params.json`) all carry
over as-is.

## Project layout

```
.
├── manage.py
├── requirements.txt
├── uchko_project/         # Django settings / root URL conf
├── learning/              # The single Django app
│   ├── views.py           # All HTTP handlers
│   ├── services.py        # Bridge between views and uchko_core
│   ├── urls.py
│   ├── templates/learning/
│   │   ├── base.html
│   │   ├── account.html
│   │   ├── practice.html
│   │   ├── progress.html
│   │   ├── curriculum.html
│   │   └── settings.html
│   ├── static/learning/css/styles.css
│   └── templatetags/uchko_extras.py
├── uchko_core/            # Untouched core logic from the Streamlit app
├── data/                  # Skills, templates, cached events / users
└── models/                # BKT params + trained risk model artifacts
```

## Quick start

```bash
python -m pip install -r requirements.txt
python manage.py migrate     # creates the sessions table
python manage.py runserver
```

Then open http://127.0.0.1:8000/ — the entry page is the user picker (mirrors
the sidebar in the Streamlit app). After you create or pick a user, you land
on `/practice/`.

## Notes

- Sessions are stored in the default Django DB-backed session backend, so
  `python manage.py migrate` is required before the first request.
- The curriculum graph is rendered server-side with matplotlib's `Agg`
  backend (no GUI needed) and served as a PNG.
- All event-logging (`solve` / `hint` / `explanation` / `start` / `end`)
  goes to the same Parquet file the Streamlit app used, so you can swap
  between the two without losing data.
