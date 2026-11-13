import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab', ROOT/'lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class ArchiveTests(unittest.TestCase):
    def fixture(self, root):
        folder=root/'saved'; (folder/'code/experiment').mkdir(parents=True)
        (folder/'code/experiment/pipeline.py').write_text("VALUE='old'\n")
        lab.save(folder/'inputs.json', [])
        lab.save(folder/'bundle-lock.json', {'files':lab.files(folder/'code'), 'inputs_sha256':lab.sha(folder/'inputs.json')})
        return folder

    def test_tampered_code_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.fixture(Path(tmp)); lab.verify_bundle(folder)
            (folder/'code/experiment/pipeline.py').write_text("VALUE='changed'\n")
            with self.assertRaisesRegex(ValueError,'bundle changed'):lab.verify_bundle(folder)

    def test_tampered_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.fixture(Path(tmp)); lab.save(folder/'inputs.json',[1])
            with self.assertRaisesRegex(ValueError,'inputs changed'):lab.verify_bundle(folder)

    def test_archived_import_ignores_later_live_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=self.fixture(root)
            live=root/'live';live.mkdir();(live/'pipeline.py').write_text("raise RuntimeError('live code was imported')\n")
            code="import sys;sys.path.insert(0,sys.argv[1]);import pipeline;print(pipeline.VALUE)"
            result=subprocess.check_output([sys.executable,'-I','-B','-c',code,str(folder/'code/experiment')],cwd=live,text=True)
            self.assertEqual(result.strip(),'old');lab.verify_bundle(folder)

    def test_dependency_version_mismatch_rejected(self):
        lock={'python':lab.platform.python_version(),'system':lab.platform.system(),'machine':lab.platform.machine(),'packages':{'pydantic':'0.0.0'}}
        with self.assertRaisesRegex(ValueError,'Dependency mismatch'):lab.activation(lock)

    def test_sample_cap_before_creating_run(self):
        with patch.object(lab,'new_folder') as create:
            with self.assertRaisesRegex(ValueError,'one and five'):lab.create('vector-v1',6)
            create.assert_not_called()

    def test_legacy_run_is_not_claimed_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'Legacy run'):lab.repeat(Path(tmp),'rerun',True)

    def test_new_run_does_not_overwrite_prior_folder(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(lab,'ROOT',Path(tmp)):
            a=lab.new_folder('test');(a/'keep.txt').write_text('original')
            b=lab.new_folder('test');self.assertNotEqual(a,b)
            self.assertEqual((a/'keep.txt').read_text(),'original')


if __name__=='__main__':unittest.main()
