"""Run from repository root: uv run --project apps/api python scripts/seed_demo.py EMAIL."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from sqlalchemy import select
from galvanise.database import SessionLocal
from galvanise.models import User
from galvanise.agents.demo import seed

if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('Usage: seed_demo.py existing-user-email')
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==sys.argv[1]))
        if not user: raise SystemExit('Register an account before seeding a demonstration project.')
        print(seed(db,user).id)
