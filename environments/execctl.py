#!/usr/bin/env python3
"""Short control calls for disk-backed native compile, geometry and render jobs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from execution_runtime import (TERMINAL, MiB, atomic_json, doctor, job_directory,
                               job_status, start_job, utc)
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=Path, default=ROOT/'execution-jobs')
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('doctor')
    a=sub.add_parser('snapshot');a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('start')
    a.add_argument('--id',required=True)
    a.add_argument('--cwd',type=Path,default=ROOT)
    a.add_argument('--threads',type=int,default=4)
    a.add_argument('--timeout',type=float,default=14400)
    a.add_argument('--memory-mb',type=int)
    a.add_argument('command',nargs=argparse.REMAINDER)
    a=sub.add_parser('status');a.add_argument('id',nargs='?')
    a=sub.add_parser('wait');a.add_argument('id');a.add_argument('--seconds',type=float,default=5)
    a=sub.add_parser('cancel');a.add_argument('id')
    args=p.parse_args()
    try:
        if args.action=='doctor':
            result=doctor(ROOT)
        elif args.action=='snapshot':
            from tools.package_delivery import archive,source_selected
            result=archive(args.output,[p for p in ROOT.rglob('*') if p.is_file() and source_selected(p)])
        elif args.action=='start':
            cmd=args.command[1:] if args.command[:1]==['--'] else args.command
            result=start_job(args.jobs,args.id,cmd,args.cwd,args.threads,args.timeout,
                             args.memory_mb*MiB if args.memory_mb is not None else None)
        elif args.action=='status':
            result=job_status(args.jobs,args.id) if args.id else [job_status(args.jobs,d.name) for d in sorted(args.jobs.glob('*')) if (d/'spec.json').exists()]
        elif args.action=='wait':
            if not 0<=args.seconds<=20:raise ValueError('A control call may wait at most 20 seconds; poll again for long jobs.')
            until=time.monotonic()+args.seconds
            while True:
                result=job_status(args.jobs,args.id)
                if result['state'] in TERMINAL or time.monotonic()>=until:break
                time.sleep(.2)
        else:
            folder=job_directory(args.jobs,args.id)
            result=job_status(args.jobs,args.id)
            if result['state'] not in TERMINAL:
                atomic_json(folder/'cancel.request',{'requested_at':utc()})
                result['cancel_requested']=True
        print(json.dumps(result,indent=2))
        return 0
    except (OSError,ValueError,RuntimeError) as exc:
        print(json.dumps({'error':str(exc)}),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
