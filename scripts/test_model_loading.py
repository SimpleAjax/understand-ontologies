"""Regression: a pinned workbench model must load without online resolution."""
import sys
import types
import unittest
from unittest.mock import Mock, patch

from pipeline import load_model


class LocalModelTests(unittest.TestCase):
    def test_pinned_local_load_never_resolves_remote_revision(self):
        api = Mock(side_effect=AssertionError('Unexpected online revision lookup'))
        constructor = Mock(return_value=object())
        with patch.dict(sys.modules, {
            'huggingface_hub': types.SimpleNamespace(HfApi=api),
            'sentence_transformers': types.SimpleNamespace(SentenceTransformer=constructor),
        }):
            _, revision = load_model('pinned-revision', local_files_only=True)
        self.assertEqual(revision, 'pinned-revision')
        self.assertTrue(constructor.call_args.kwargs['local_files_only'])
        api.assert_not_called()

    def test_offline_requires_pinned_revision(self):
        with self.assertRaises(ValueError):
            load_model(None, local_files_only=True)


if __name__ == '__main__':
    unittest.main()
