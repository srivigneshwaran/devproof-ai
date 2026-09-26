"""Pytest configuration — add backend/ to sys.path so modules resolve."""
import sys
import os

# Ensure the backend directory (this file's parent) is on sys.path so that
# 'import llm', 'import main', 'import db', etc. all resolve correctly.
sys.path.insert(0, os.path.dirname(__file__))
