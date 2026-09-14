import unittest
from unittest.mock import Mock

from kosis_client import build_kosis_url, fetch_kosis_payload, redact_api_key


class KosisClientTests(unittest.TestCase):
    def test_build_url_preserves_literal_plus_separators(self):
        url = build_kosis_url("TEST_KEY=", months=72)
        self.assertIn("apiKey=TEST_KEY=", url)
        self.assertIn("itmId=T10+T20+T21+T22+", url)
        self.assertIn("objL1=00+", url)
        self.assertIn("newEstPrdCnt=72", url)
        self.assertNotIn("%2B", url)

    def test_fetch_defaults_to_ssl_verification_disabled(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"PRD_DE": "202608", "DT": "100"}]
        fake_get = Mock(return_value=response)

        payload, request_url = fetch_kosis_payload("TEST_KEY=", months=72, get=fake_get)

        self.assertEqual(payload, response.json.return_value)
        self.assertIn("itmId=T10+T20+T21+T22+", request_url)
        fake_get.assert_called_once_with(request_url, timeout=30, verify=False)

    def test_redacts_api_key_from_diagnostic_url(self):
        url = build_kosis_url("SECRET_KEY=", months=72)
        safe = redact_api_key(url)
        self.assertNotIn("SECRET_KEY", safe)
        self.assertIn("apiKey=***", safe)


if __name__ == "__main__":
    unittest.main()

class KosisHistoryTests(unittest.TestCase):
    def test_build_url_uses_explicit_period_range_without_recent_count(self):
        from kosis_client import build_kosis_url
        url = build_kosis_url(
            "TEST_KEY=",
            months=None,
            start_prd_de="201701",
            end_prd_de="202612",
        )
        self.assertIn("startPrdDe=201701", url)
        self.assertIn("endPrdDe=202612", url)
        self.assertNotIn("newEstPrdCnt=", url)

    def test_chunked_history_splits_large_request_and_combines_rows(self):
        from unittest.mock import Mock
        from kosis_client import fetch_kosis_history_payload

        calls = []

        def fake_get(url, timeout, verify):
            calls.append(url)
            response = Mock()
            response.raise_for_status.return_value = None
            if "newEstPrdCnt=1" in url:
                response.json.return_value = [{"PRD_DE": "202608", "DT": "100", "C2": "C26"}]
            else:
                import re
                start = re.search(r"startPrdDe=(\d{6})", url).group(1)
                end = re.search(r"endPrdDe=(\d{6})", url).group(1)
                response.json.return_value = [
                    {"PRD_DE": start, "DT": "100", "C2": "C26"},
                    {"PRD_DE": end, "DT": "101", "C2": "C26"},
                ]
            return response

        payload, urls = fetch_kosis_history_payload(
            "TEST_KEY=",
            months=240,
            chunk_months=120,
            get=fake_get,
        )

        # One discovery call + twenty non-overlapping 12-month range calls.
        self.assertEqual(len(calls), 21)
        self.assertEqual(len(urls), 21)
        self.assertTrue(any("startPrdDe=" in u and "endPrdDe=" in u for u in urls))
        self.assertGreaterEqual(len(payload), 4)

    def test_scalar_error_object_raises_clear_kosis_error(self):
        from unittest.mock import Mock
        from kosis_client import KosisApiError, fetch_kosis_payload

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"err": "30", "errMsg": "데이터가 존재하지 않습니다."}
        fake_get = Mock(return_value=response)

        with self.assertRaises(KosisApiError) as ctx:
            fetch_kosis_payload("TEST_KEY=", months=720, get=fake_get)
        self.assertIn("데이터가 존재하지 않습니다", str(ctx.exception))
        self.assertEqual(ctx.exception.err, "30")

class KosisChunkSafetyTests(unittest.TestCase):
    def test_history_chunk_size_is_capped_below_large_response_limit(self):
        from unittest.mock import Mock
        from kosis_client import fetch_kosis_history_payload

        calls = []

        def fake_get(url, timeout, verify):
            calls.append(url)
            response = Mock()
            response.raise_for_status.return_value = None
            if "newEstPrdCnt=1" in url:
                response.json.return_value = [{"PRD_DE": "202608", "DT": "100", "C2": "C26"}]
            else:
                response.json.return_value = [{"PRD_DE": "202608", "DT": "100", "C2": "C26"}]
            return response

        fetch_kosis_history_payload(
            "TEST_KEY=",
            months=120,
            chunk_months=120,
            get=fake_get,
        )

        # Twelve months already returns roughly 5,000 rows, so cap at 12 months.
        range_calls = [u for u in calls if "startPrdDe=" in u]
        self.assertEqual(len(range_calls), 10)

    def test_history_skips_only_no_data_ranges_and_keeps_later_rows(self):
        from kosis_client import fetch_kosis_history_payload

        def fake_get(url, timeout, verify):
            response = Mock(); response.raise_for_status.return_value = None
            if "newEstPrdCnt=1" in url:
                response.json.return_value = [{"PRD_DE":"202608","DT":"1","C2":"C26"}]
            elif "startPrdDe=202409" in url:
                response.json.return_value = {"err":"30","errMsg":"데이터가 존재하지 않습니다."}
            else:
                response.json.return_value = [{"PRD_DE":"202607","DT":"2","C2":"C26"}]
            return response

        rows, _ = fetch_kosis_history_payload("TEST_KEY=", months=24, get=fake_get)
        self.assertEqual(len(rows), 1)
