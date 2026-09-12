import json
import unittest
from github_similarity import prepare_github_source, source_similarity, source_tokens


def payload(files, url='https://github.com/student/quest'):
    return json.dumps({'repo_url': url, 'ref': 'main', 'files': [
        {'name': name, 'content': content} for name, content in files]}, ensure_ascii=False)


class GitHubSimilarityTests(unittest.TestCase):
    def compare(self, first, second):
        return source_similarity(prepare_github_source(first), prepare_github_source(second))

    def test_https_envelopes_do_not_create_identical_solutions(self):
        a = payload([('quest.py', 'def play():\n    name = input("Имя?")\n    print(name)\nplay()')])
        b = payload([('game.py', 'from math import sqrt\nvalues = [sqrt(x) for x in range(100)]')], 'https://github.com/other/game')
        self.assertLess(self.compare(a, b), 75)

    def test_same_source_renamed_and_reordered_is_identical(self):
        a = payload([('repo-main/main.py', 'print("https://example.test") # comment'), ('repo-main/util.py', 'x=10//3')])
        b = payload([('other/foo.py', 'x = 10 // 3'), ('other/bar.py', 'print("https://example.test")')])
        self.assertEqual(self.compare(a, b), 100)

    def test_shared_readme_and_dependencies_do_not_count(self):
        common = [('README.md', 'same text' * 10000), ('root/.venv/lib/copied.py', 'print(42)' * 10000)]
        self.assertEqual(prepare_github_source(payload(common)), ())
        self.assertEqual(self.compare(payload(common), payload(common)), 0)

    def test_python_division_and_string_urls_are_preserved(self):
        tokens = source_tokens('x=10//3\nurl="https://example.test"\nprint("not a # comment") # actual comment', '.py')
        self.assertIn('//', tokens)
        self.assertIn('"https://example.test"', tokens)
        self.assertIn('"not a # comment"', tokens)
        self.assertNotIn('actual', tokens)

    def test_invalid_pending_empty_and_large_payloads(self):
        for raw in ['not json', '[]', '{"repo_url":"https://github.com/x/y"}']:
            with self.assertRaises(ValueError):
                prepare_github_source(raw)
        self.assertEqual(self.compare(payload([]), payload([])), 0)
        with self.assertRaises(ValueError):
            prepare_github_source(payload([('x.py', 'x=1' * 50)]), max_chars=100)

    def test_invalid_python_falls_back_without_crashing_or_losing_content(self):
        self.assertTrue(source_tokens('x = (\n"https://example.test"', '.py'))


if __name__ == '__main__':
    unittest.main()
