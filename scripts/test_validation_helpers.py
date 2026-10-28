"""Standard-library-only runner regression tests. No Django or database access."""
import unittest
from validate_dic_backend import missing_test_labels


class LabelCoverageTests(unittest.TestCase):
    def test_module_class_and_method_labels(self):
        method = 'dic.tests.RegistrationApiTests.test_registration'
        self.assertEqual(missing_test_labels(['dic.tests', 'dic.tests.RegistrationApiTests', method], [method], []), [])

    def test_skipped_missing_and_similar_prefixes_fail(self):
        method = 'dic.tests.RegistrationApiTests.test_registration'
        label = 'dic.tests.RegistrationApiTests'
        self.assertEqual(missing_test_labels([label], [method], [method]), [label])
        self.assertEqual(missing_test_labels([label], [], []), [label])
        self.assertEqual(missing_test_labels([label], [label+'Other.test_registration'], []), [label])


if __name__ == '__main__':
    unittest.main()
