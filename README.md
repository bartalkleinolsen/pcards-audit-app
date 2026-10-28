# OSU P-Card Audit Workspace

SDU AI in Accounting and Business — Assignment 1, Case 2, Part IV.

**Two tabs:**
1. **Ask the Database** — question in natural language → Gemini generates a SQLite SELECT → read-only query → results and generated SQL shown to auditor.
2. **Prohibited Purchases** — choose a year (2010–2014) and search the description field or the vendor field independently. Matching transactions appear in a searchable table and can be exported as CSV.

## How to publish (GitHub + Streamlit Community Cloud)

1. Create a new public GitHub repository, e.g. `pcards-audit-app`.
2. Copy the **contents of this project folder** into the repository's local folder. Include `app.py`, `ai_utils.py`, `db_utils.py`, `requirements.txt`, `.streamlit/config.toml`, and **`data/pcards.db.gz`**. The gzip data file is required. Push the changes with GitHub Desktop. Do not upload any API key or `.streamlit/secrets.toml`.
3. Sign in at <https://share.streamlit.io> and choose **Create app** → **Yup, I have an app**. Choose the repository, `main` branch, and entrypoint `app.py`.
4. In **Advanced settings → Secrets**, privately paste this (replace the placeholder with your own key):

   ```toml
   GEMINI_API_KEY = "PASTE_YOUR_PRIVATE_KEY_HERE"
   GEMINI_MODEL = "gemini-3.5-flash-lite"
   ```

   **Never commit this secret to GitHub or send it to anybody.** Do not paste the key into public screenshots.
5. Deploy. Test the dashboard with Year 2014, Vendor keyword `POST`, Description keyword `UNLEADED`. Test the AI with **Which 10 employees spent the most in 2014?**
6. Submit the live Streamlit URL and public GitHub repository URL alongside the completed Parts II–III document.

If a deployed app runs without a valid API key, the keyword-search dashboard still works, but the AI question form remains unavailable until the key is set.

## Run locally (optional)

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

For local AI use, set the environment variable `GEMINI_API_KEY` or add a **local, untracked** `.streamlit/secrets.toml`.

## Technical and audit notes

- The original professor-provided SQLite database is bundled as compressed `data/pcards.db.gz`. It is expanded in temporary storage at runtime; the archive is not sent to Gemini.
- All queries run against a **read-only** SQLite connection. AI-generated SQL is constrained to single SELECT/CTE statements, SQLite's authorizer blocks modifications and nonapproved functions, and execution has a timeout and a row limit.
- Natural language questions and schema information are sent to Gemini. No database rows are sent to the model by the application.
- Keyword searches use bound parameters and escape SQL wildcard characters, rather than combining raw keyword text into a query.
- User-facing results may be incomplete when more matches exist than the result preview. The UI reports the actual match count and indicates any preview limit.
- Many transactions have generic descriptions, and a vendor's MCC does not establish what was purchased. All apparent exceptions require supporting documentation and professional judgment.
- Data license: the supplied educational database is based on Oklahoma P-card data under the Open Database License (ODbL) / Database Contents License (DbCL). The academic case warns that data may have been modified for teaching; do not draw conclusions about named individuals.
- This is an educational prototype, not a security-reviewed production audit system.
