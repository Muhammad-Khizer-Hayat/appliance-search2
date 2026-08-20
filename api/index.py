"""
Vercel serverless entrypoint.

Vercel's Python runtime looks for a WSGI-compatible `app` object in
this file. We simply build the real Flask app from app.py and expose
it here — no logic duplication.
"""
import os
import sys

# Make the project root importable (api/ is one level below root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app

app = create_app()
