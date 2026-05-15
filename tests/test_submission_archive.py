import io
import json
import unittest
import zipfile

import submission_archive

extract_data_from_zipfile = submission_archive.extract_data_from_zipfile


class SubmissionArchiveTests(unittest.TestCase):
    def _zip_bytes(self, entries):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zip_file:
            for name, content in entries.items():
                zip_file.writestr(name, content)
        return archive.getvalue()

    def _names_from_archive(self, archive_bytes):
        payload = extract_data_from_zipfile(archive_bytes)
        self.assertIsNotNone(payload)
        return [item["name"] for item in json.loads(payload)]

    def test_extracts_files_from_nested_directories(self):
        archive_bytes = self._zip_bytes({
            "main.py": "print(1)",
            "src/nested.py": "print(2)",
            "src/deeper/inside.js": "console.log(3)",
        })

        self.assertEqual(
            self._names_from_archive(archive_bytes),
            ["main.py", "src/nested.py", "src/deeper/inside.js"],
        )

    def test_expands_nested_zip_files_for_display(self):
        nested_zip = self._zip_bytes({
            "inner.py": "print(2)",
            "lib/helper.py": "print(3)",
        })
        archive_bytes = self._zip_bytes({
            "main.py": "print(1)",
            "bundle.zip": nested_zip,
        })

        self.assertEqual(
            self._names_from_archive(archive_bytes),
            ["main.py", "bundle.zip/inner.py", "bundle.zip/lib/helper.py"],
        )

    def test_rejects_too_many_files(self):
        original_limit = submission_archive.MAX_ARCHIVE_FILE_COUNT
        try:
            submission_archive.MAX_ARCHIVE_FILE_COUNT = 2
            archive_bytes = self._zip_bytes({
                "one.py": "1",
                "two.py": "2",
                "three.py": "3",
            })

            self.assertIsNone(extract_data_from_zipfile(archive_bytes))
        finally:
            submission_archive.MAX_ARCHIVE_FILE_COUNT = original_limit

    def test_large_files_are_rendered_as_placeholders(self):
        original_limit = submission_archive.MAX_TEXT_FILE_BYTES
        try:
            submission_archive.MAX_TEXT_FILE_BYTES = 4
            archive_bytes = self._zip_bytes({"large.txt": "12345"})
            payload = extract_data_from_zipfile(archive_bytes)
            files = json.loads(payload)

            self.assertEqual(files[0]["name"], "large.txt")
            self.assertTrue(files[0]["is-binary"])
            self.assertIn("5 байт", files[0]["content"])
        finally:
            submission_archive.MAX_TEXT_FILE_BYTES = original_limit


if __name__ == "__main__":
    unittest.main()
