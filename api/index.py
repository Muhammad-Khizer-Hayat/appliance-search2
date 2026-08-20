import os
import sys

# Make the project root importable (api/ is one level below root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app

app = create_app()