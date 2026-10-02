#!/usr/bin/env python3
"""Verify a temporary recovery package, without overwriting a saved release."""
import json
import tempfile
from pathlib import Path
from release_bundle import pack,verify
ROOT=Path(__file__).resolve().parents[1]
def main():
 with tempfile.TemporaryDirectory(prefix='edgeai-package-') as td:
  archive=Path(td)/'snapshot.zip';pack(ROOT,archive);r=verify(archive)
  print(json.dumps({'status':r['status'],'files':r['files'],'sha256':r['sha256'],'temporary_smoke_only':True},indent=2))
if __name__=='__main__':main()
