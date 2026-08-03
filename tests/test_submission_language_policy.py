import unittest
from types import SimpleNamespace

from paste_server import _task_submission_language_error


class SubmissionLanguagePolicyTests(unittest.TestCase):
    def test_image_task_requires_an_image(self):
        task = SimpleNamespace(lang='image')
        self.assertIsNotNone(_task_submission_language_error(task, 'cpp'))
        self.assertIsNone(_task_submission_language_error(task, 'image'))

    def test_non_image_task_rejects_an_image_payload(self):
        task = SimpleNamespace(lang='cpp')
        self.assertIsNotNone(_task_submission_language_error(task, 'image'))
        self.assertIsNone(_task_submission_language_error(task, 'cpp'))

    def test_standalone_submission_keeps_legacy_language_choice(self):
        self.assertIsNone(_task_submission_language_error(None, 'image'))


if __name__ == '__main__':
    unittest.main()
