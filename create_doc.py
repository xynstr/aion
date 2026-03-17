
import sys
from pathlib import Path
try:
    from docx import Document
except ImportError:
    print("Error: python-docx is not installed. Please run 'pip install python-docx'.")
    sys.exit(1)

# Simple argument parsing
if len(sys.argv) != 3:
    print("Usage: python create_doc.py <path_to_docx> <content>")
    sys.exit(1)

file_path_str = sys.argv[1]
content = sys.argv[2]

file_path = Path(file_path_str)

try:
    document = Document()
    document.add_paragraph(content)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(file_path)
    print(f"Success: Created {file_path}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
