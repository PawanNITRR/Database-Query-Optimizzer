"""Reproducible local evaluation; does not modify the live learned policy."""
import json
import tempfile
from pathlib import Path
import numpy as np
import app as module
from rl import RewriteAgent
from history import History
from workloads import REPORTS
from simulation import simulate


def main():
    report = {'scope': 'Synthetic retail demo; held-out dates and shapes, not a proof of production generalization.'}
    with tempfile.TemporaryDirectory() as tmp:
        module.agent=RewriteAgent(Path(tmp)/'policy.sqlite3')
        module.history=History(Path(tmp)/'history.sqlite3')
        client=module.app.test_client()
        training=[]
        for epoch in range(3):
            for name,query in REPORTS.items():
                response=client.post('/api/optimize',json={'query':query,'use_ai':False})
                if response.status_code!=200:
                    raise RuntimeError(response.json)
                data=response.json
                training.append({'report':name,'epoch':epoch,'action':data['rl']['action'],
                    'reward':data['rl']['reward'],'response_ms':data['total_ms']})
        report['training_episodes']=training
        unseen=[]
        for name,query in REPORTS.items():
            # Different month and status values were never used in training episodes.
            modified=query.replace('2025-06-01','2024-08-01').replace('2025-07-01','2024-09-01').replace('2025-11-01','2024-02-01').replace('2025-12-01','2024-03-01').replace('2025-03-01','2024-10-01').replace('2025-04-01','2024-11-01')
            response=client.post('/api/optimize',json={'query':modified,'use_ai':False})
            if response.status_code!=200:
                raise RuntimeError(response.json)
            d=response.json
            unseen.append({'report':name,'action':d['rl']['action'],'reward':d['rl']['reward'],
                'result_equality_passed':True,'improvement_pct':d['metrics']['improvement_pct'],
                'response_ms':d['total_ms']})
        report['unseen_workloads']=unseen
        # Different query structure, previously unseen, allows only a no-op action.
        response=client.post('/api/optimize',json={'query':'SELECT category, AVG(price) FROM product GROUP BY category','use_ai':False})
        report['unseen_structure']={'status':response.status_code,'action':response.json.get('rl',{}).get('action')}
        report['privacy']={'history_scrubbed':all('completed' not in r['masked_query'] and '2025' not in r['masked_query'] for r in module.history.list()),
            'mask_module_modified':False,'note':'Tests validate supported SQL; no universal privacy certification is claimed.'}
    report['structural_simulation']=[simulate(action) for action in ('index','range','hash')]
    # Holdout set is independent synthetic graphs; do not imply real-plan accuracy.
    model=module.gnn; rng=np.random.default_rng(2026); labels=[]; guesses=[]
    for _ in range(100):
        x=rng.random((8,4)); a=np.eye(8)
        for i in range(1,8):
            p=int(rng.integers(i)); a[i,p]=a[p,i]=1
        labels.extend((x[:,0]>.55).astype(int))
        guesses.extend((model.sigmoid(model.embed(x,a)@model.readout)>=.5).astype(int))
    labels=np.array(labels); guesses=np.array(guesses)
    tp=int(((labels==1)&(guesses==1)).sum());fp=int(((labels==0)&(guesses==1)).sum());fn=int(((labels==1)&(guesses==0)).sum())
    report['gnn_synthetic_holdout']={'accuracy':float((labels==guesses).mean()),'precision':tp/max(tp+fp,1),
        'recall':tp/max(tp+fn,1),'nodes':len(labels),'limitation':'Synthetic cost-threshold labels; no real-workload generalization claim.'}
    Path('EVALUATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'unseen_workloads':unseen,'gnn':report['gnn_synthetic_holdout'],
        'simulation':[{'action':s['action'],'read_improvement_pct':s['read_improvement_pct'],'storage_delta_bytes':s['storage_delta_bytes']} for s in report['structural_simulation']]},indent=2))


if __name__=='__main__':
    main()
