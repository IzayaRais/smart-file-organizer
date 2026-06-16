import os
import sys
import shutil
import unittest
import subprocess
import json
from pathlib import Path

class TestFileOrganizer(unittest.TestCase):
    def _safe_remove_test_dir(self):
        import time
        for i in range(10):
            try:
                if self.test_dir.exists():
                    shutil.rmtree(self.test_dir)
                return
            except PermissionError:
                time.sleep(0.2)
        # If still failing, try to delete whatever we can
        if self.test_dir.exists():
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    def setUp(self):
        self.test_dir = Path("./temp_test_organizer").resolve()
        self._safe_remove_test_dir()
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        self.files_to_create = {
            "doc1.pdf": "PDF document content here",
            "doc2.docx": "Word document content here",
            "img1.png": "Some PNG binary data dummy text",
            "img2.jpg": "Some JPG binary data dummy text",
            "code1.py": "print('hello world')",
            "archive1.zip": "Zip file contents",
            "empty1.txt": "", 
            "empty2.log": "", 
            "doc1_dupe.pdf": "PDF document content here", 
            "img1_dupe.png": "Some PNG binary data dummy text", 
            "subfolder/doc3.txt": "Text inside subfolder",
            "subfolder/img3.webp": "Webp image inside subfolder",
        }
        
        for name, content in self.files_to_create.items():
            file_path = self.test_dir / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            else:
                file_path.touch()

    def tearDown(self):
        self._safe_remove_test_dir()

    def run_organizer(self, args):
        cmd = [sys.executable, "organizer.py"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        return result

    def test_dry_run(self):
        result = self.run_organizer(["-t", str(self.test_dir), "-m", "type", "--dry-run", "--yes"])
        self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        for name in self.files_to_create.keys():
            self.assertTrue((self.test_dir / name).exists(), f"File {name} should not be moved in dry-run")

    def test_live_organization_by_type(self):
        result = self.run_organizer(["-t", str(self.test_dir), "-m", "type", "--yes"])
        self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        
        self.assertTrue((self.test_dir / "Documents" / "doc1.pdf").exists())
        self.assertTrue((self.test_dir / "Documents" / "doc2.docx").exists())
        self.assertTrue((self.test_dir / "Images" / "img1.png").exists())
        self.assertTrue((self.test_dir / "Images" / "img2.jpg").exists())
        self.assertTrue((self.test_dir / "Code_Scripts" / "code1.py").exists())
        self.assertTrue((self.test_dir / "Archives" / "archive1.zip").exists())
        
        self.assertTrue((self.test_dir / "Previous_Folders" / "subfolder").exists())
        self.assertTrue((self.test_dir / "Documents" / "doc3.txt").exists())
        self.assertTrue((self.test_dir / "Images" / "img3.webp").exists())
        
        self.assertTrue((self.test_dir / "Empty_Files" / "empty1.txt").exists())
        self.assertTrue((self.test_dir / "Empty_Files" / "empty2.log").exists())
        
        self.assertFalse((self.test_dir / "doc1_dupe.pdf").exists())
        self.assertFalse((self.test_dir / "img1_dupe.png").exists())
        
        self.assertTrue((self.test_dir / "organization_log.txt").exists())
        self.assertTrue((self.test_dir / ".organizer_history.json").exists())

    def test_undo_functionality(self):
        self.run_organizer(["-t", str(self.test_dir), "-m", "type", "--yes"])
        
        result = self.run_organizer(["-t", str(self.test_dir), "--undo", "--yes"])
        self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        
        self.assertTrue((self.test_dir / "doc1.pdf").exists())
        self.assertTrue((self.test_dir / "doc2.docx").exists())
        self.assertTrue((self.test_dir / "img1.png").exists())
        self.assertTrue((self.test_dir / "img2.jpg").exists())
        self.assertTrue((self.test_dir / "code1.py").exists())
        self.assertTrue((self.test_dir / "archive1.zip").exists())
        self.assertTrue((self.test_dir / "empty1.txt").exists())
        self.assertTrue((self.test_dir / "empty2.log").exists())
        self.assertTrue((self.test_dir / "subfolder" / "doc3.txt").exists())
        self.assertTrue((self.test_dir / "subfolder" / "img3.webp").exists())
        
        self.assertFalse((self.test_dir / "Documents").exists())
        self.assertFalse((self.test_dir / "Images").exists())
        self.assertFalse((self.test_dir / "Code_Scripts").exists())
        self.assertFalse((self.test_dir / "Archives").exists())
        self.assertFalse((self.test_dir / "Empty_Files").exists())
        self.assertFalse((self.test_dir / "Previous_Folders").exists())
        
        self.assertFalse((self.test_dir / ".organizer_history.json").exists())

if __name__ == "__main__":
    unittest.main()
