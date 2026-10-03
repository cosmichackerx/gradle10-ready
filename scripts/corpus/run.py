"""Scan a directory of cloned repositories and print findings per rule. usage: run.py CLONES_DIR OUT.json"""
import sys, os, collections, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
from gradle10_ready.scan import scan
root = sys.argv[1]
per_rule = collections.Counter(); repos_rule = collections.defaultdict(set); with_any = 0; withfile = 0; n=0; out=[]
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p): continue
    n += 1
    r = scan(p)
    if r.files_scanned: withfile += 1
    if r.findings: with_any += 1
    for f in r.findings:
        per_rule[f.rule] += 1; repos_rule[f.rule].add(d)
        out.append((d, f.rule, f.severity, f.file, f.line, f.snippet))
print(n, 'repos,', withfile, 'with gradle files,', with_any, 'with findings')
for k, v in per_rule.most_common(): print(f'{k:30} {v:5} findings in {len(repos_rule[k])} repos')
json.dump(out, open(sys.argv[2], 'w'))
