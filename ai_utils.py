"""Gemini natural-language -> SQL conversion; key never included in repository."""
from __future__ import annotations

import json

MODEL = "gemini-3.5-flash-lite"

SQL_INSTRUCTIONS = """
You are an auditor's SQL assistant for a READ-ONLY SQLite database.
Only generate one valid SQLite SELECT statement (WITH CTEs are also allowed).
The database has ONE table: pcards, with fields:
Year INTEGER (2010-2014), Month INTEGER (1-12),
FullName TEXT (anonymized employee label e.g. 'Employee ABCD1234'), ID INTEGER,
AgencyNumber INTEGER (1000), AgencyName TEXT ('OKLAHOMA STATE UNIVERSITY'),
CardholderLastName TEXT, CardholderFirstInitial TEXT,
Description TEXT, Amount REAL (negative = credit), Vendor TEXT,
TransactionDate TEXT and PostedDate TEXT (stored as '7/26/2014 0:00:00'),
MCC TEXT (merchant category description).

IMPORTANT INSTRUCTIONS:
- Answer by selecting from the table, not by inventing results.
- Include AgencyNumber=1000 in transactions queries.
- When no year is specified, default to Year=2014; if another year or all years is specified, honor it.
- Use SUM(Amount) for net expenditure and specify this convention in explanation.
- If asked about charges/purchases exclusively, filter Amount > 0.
- In SQLite, chronological date ordering is NOT lexicographic for 'm/d/yyyy'. Use Year, Month and
  CAST(SUBSTR(TransactionDate, INSTR(TransactionDate, '/')+1) AS INTEGER) where useful,
  or strftime only if you first convert the date to ISO.
- If the user asks to test fraud or control breaches, explicitly frame results as POSSIBLE
  exceptions. Merchant code and description cannot establish actual items or intent.
- Never generate SQL writes, PRAGMA, ATTACH, SELECT of sqlite_master, schema discovery,
  file access, functions with side effects or multiple statements.
- Prefer explicit output column aliases and clear ordering.
- Return a JSON OBJECT with keys: sql (one SELECT statement) and explanation (short English text).
- If question cannot be answered from these columns, return sql='SELECT 0 AS NotAvailable'
  and explanation describing missing fields, not invented data.
"""


def question_to_sql(question: str, api_key: str, model: str = MODEL) -> tuple[str, str, int | None]:
    if not api_key:
        raise ValueError("Gemini API key missing")
    if len(question.strip()) < 4 or len(question) > 1200:
        raise ValueError("Question must be between 4 and 1200 characters")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=question.strip(),
        config=types.GenerateContentConfig(
            system_instruction=SQL_INSTRUCTIONS,
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=1300,
        ),
    )
    if not response.text:
        raise RuntimeError("The AI model returned no text")
    payload = json.loads(response.text)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected AI response format")
    sql = str(payload.get("sql", ""))
    explanation = str(payload.get("explanation", ""))
    tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
    return sql, explanation, tokens
