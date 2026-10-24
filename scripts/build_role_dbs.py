"""Build role databases: python -m scripts.build_role_dbs california_schools [--canary]"""
import sys

from agent import roles

if __name__ == "__main__":
    db_id = sys.argv[1]
    for r in roles.role_names(db_id):
        p = roles.build(db_id, r, canary="--canary" in sys.argv)
        print(r, p)
