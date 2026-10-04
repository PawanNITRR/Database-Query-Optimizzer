"""One live local AI check, preserving masking and saving only numeric evidence."""
import json
from pathlib import Path
from time import perf_counter
from privacy import Mask
from optimizer import optimize
from database import connect, configure, explain, compare
from gnn import PlanGNN
from workloads import REPORTS


started=perf_counter()
report={'local_service':'Ollama','raw_query_sent':False}
try:
    mask=Mask(REPORTS['products'])
    with connect() as conn:
        configure(conn)
        graph=PlanGNN().analyze(explain(conn,mask.tree.sql(dialect='postgres'))['Plan'])
        candidate,reason,engine=optimize(mask.sql,graph,True)
        restored=mask.restore(candidate)
        metrics=compare(conn,mask.tree.sql(dialect='postgres'),restored)
    report.update(status='passed',result_equality_passed=True,changed=restored!=mask.tree.sql(dialect='postgres'),metrics=metrics)
except Exception as exc:
    report.update(status='rejected_or_unavailable',reason=str(exc)[:300],
                  cause_type=type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
                  cause_message=str(exc.__cause__)[:200] if exc.__cause__ else '')
report['response_ms']=round((perf_counter()-started)*1000,1)
Path('AI_EVALUATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
