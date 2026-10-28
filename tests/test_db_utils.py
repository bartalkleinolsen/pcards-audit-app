from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_utils import (QueryRejected, connect, get_overview, get_year_summary,
                      run_readonly_query, search_field, validate_query)


class DataTests(unittest.TestCase):
    def test_overview_and_year(self):
        overview = get_overview()
        self.assertEqual(overview['transactions'], 489178)
        self.assertEqual(overview['years'], [2014, 2013, 2012, 2011, 2010])
        self.assertEqual(get_year_summary(2014)['transactions'], 116031)

    def test_search_description(self):
        rows, count = search_field(2014, 'Description', 'regular unleaded')
        self.assertGreater(count, 0)
        self.assertGreater(len(rows), 0)

    def test_search_vendor(self):
        rows, count = search_field(2014, 'Vendor', 'POST')
        self.assertGreaterEqual(count, len(rows))
        self.assertGreater(count, 0)

    def test_limited_aggregation(self):
        frame, truncated = run_readonly_query(
            'SELECT FullName, ROUND(SUM(Amount),2) as TotalSpent FROM pcards '
            'WHERE Year = 2014 GROUP BY FullName ORDER BY TotalSpent DESC LIMIT 10'
        )
        self.assertEqual(len(frame), 10)
        self.assertFalse(truncated)
        self.assertGreater(frame.iloc[0]['TotalSpent'], 1500000)

    def test_with(self):
        frame, _ = run_readonly_query(
            'WITH t AS (SELECT Amount FROM pcards WHERE Year=2014) SELECT COUNT(*) AS n FROM t'
        )
        self.assertEqual(int(frame.iloc[0]['n']), 116031)

    def test_read_only(self):
        for sql in ['DELETE FROM pcards', 'DROP TABLE pcards', 'PRAGMA table_info(pcards)',
                    'SELECT * FROM sqlite_master', 'SELECT load_extension("x")',
                    'SELECT * FROM pcards; DELETE FROM pcards']:
            with self.subTest(sql=sql):
                with self.assertRaises(QueryRejected):
                    run_readonly_query(sql)

    def test_literal_wildcard_search(self):
        frame, count = search_field(2014, 'Description', '%')
        with connect() as c:
            actual = c.execute('SELECT count(*) FROM pcards WHERE Year=2014 AND Description LIKE ?', ('%\\%%',)).fetchone()[0]
        self.assertGreaterEqual(count, 0)
        self.assertLess(count, 116031)

    def test_truncation(self):
        frame, truncated = run_readonly_query('SELECT ID FROM pcards WHERE Year=2014', max_rows=5)
        self.assertTrue(truncated)
        self.assertEqual(len(frame), 5)


if __name__ == '__main__':
    unittest.main()
