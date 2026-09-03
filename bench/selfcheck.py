#!/usr/bin/env python3
"""自检:每个场景 setup → oracle 写正确答案 → verify 必须通过;顺便报告生成物体积。
用法:python3 bench/selfcheck.py [scenario ...]"""
import os, sys, json, importlib.util, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def size(root):
    n = 0
    for dp, dn, fns in os.walk(root):
        if '.truth' in dp or '.git' in dp: continue
        for fn in fns: n += os.path.getsize(os.path.join(dp, fn))
    return n
names = sys.argv[1:] or sorted(d for d in os.listdir(os.path.join(HERE, 'scenarios')) if os.path.isdir(os.path.join(HERE, 'scenarios', d)))
allok = True
for name in names:
    sdir = os.path.join(HERE, 'scenarios', name)
    root = tempfile.mkdtemp(prefix='foldbench-' + name + '-')
    sys.path.insert(0, sdir)
    try:
        setup = load(os.path.join(sdir, 'setup.py'), name + '_setup'); setup.setup(root)
        sz = size(root)
        verify = load(os.path.join(sdir, 'verify.py'), name + '_verify')
        ok0, d0 = verify.verify(root)                      # 未作答:必须不通过
        oracle = load(os.path.join(sdir, 'oracle.py'), name + '_oracle'); oracle.solve(root)
        ok1, d1 = verify.verify(root)                      # oracle 作答:必须通过
        meta = json.load(open(os.path.join(sdir, 'meta.json'))); prompts = json.load(open(os.path.join(sdir, 'prompts.json')))
        status = 'OK ' if (ok1 and not ok0) else 'BAD'
        allok &= (ok1 and not ok0)
        print('%s %-20s size=%6dK turns=%d/%d  blank→%s  oracle→%s %s' % (status, name, sz // 1000, len(prompts), meta['turns'], 'fail' if not ok0 else 'PASS?!', 'pass' if ok1 else 'FAIL', '' if ok1 else d1[:160]))
    except Exception as e:
        allok = False; print('ERR %-20s %s' % (name, str(e)[:200]))
    finally:
        sys.path.pop(0); shutil.rmtree(root, ignore_errors=True)
sys.exit(0 if allok else 1)
