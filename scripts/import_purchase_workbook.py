"""Run on the configured server: python -m scripts.import_purchase_workbook FILE.

Never commit the source workbook. All sheets are archived privately in PostgreSQL;
only Input becomes ledger rows. UserList never creates website accounts.
"""
import argparse
from pathlib import Path
import vera_purchase_store as store
from vera_postgres import get_engine


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('file',type=Path)
    parser.add_argument('--actor',required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    content=args.file.read_bytes()
    rows=store.parse_workbook(content)
    if args.dry_run:
        print(f'rows={len(rows)} total={sum(r["amount"] for r in rows)}')
        return
    with get_engine().begin() as conn:
        store.ensure_schema(conn)
        result=store.import_workbook(conn,content,args.actor,rows=rows)
    print(f'rows={result["source_rows"]} inserted={result["inserted"]} skipped={result["skipped"]} total={result["total"]}')


if __name__=='__main__': main()
