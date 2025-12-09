#!/usr/bin/env python3
import os, zipfile, datetime, argparse
def gather(root):
  for base,_,files in os.walk(root):
    for f in files:
      p=os.path.join(base,f); rel=os.path.relpath(p,root)
      if rel.startswith(('.venv','__pycache__','.git','.idea')): continue
      if f.endswith(('.pyc','.pyo','.DS_Store','.autofix.bak')): continue
      yield p, rel
def main():
  ap=argparse.ArgumentParser(); ap.add_argument('--name',default='bus_release'); ap.add_argument('--outdir',default='.');
  a=ap.parse_args(); date=datetime.date.today().isoformat(); out=os.path.join(a.outdir,f"{a.name}_{date}.zip")
  root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p,rel in gather(root): z.write(p,arcname=rel)
  print(out)
if __name__=='__main__': main()
