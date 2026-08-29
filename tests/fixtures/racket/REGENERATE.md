# Regenerating `tests/fixtures/racket_oracle.json`

The frozen file is the output of Racket's own expander against the `.rkt`
fixtures in this directory. It exists so `tests/test_racket_fidelity.py` can
gate the hard-fail buckets **on machines with no Racket installed**, which
includes CI.

Regenerate only when a fixture changes, and record the Racket version:

```bash
racket benchmarks/racket_fidelity/oracle.rkt tests/fixtures/racket/*.rkt \
  | python3 -c "
import json,sys,os
out={}
for line in sys.stdin:
    line=line.strip()
    if line.startswith('{'):
        rec=json.loads(line); rec['file']=os.path.basename(rec['file']); out[rec['file']]=rec
import subprocess
ver=subprocess.run(['racket','--version'],capture_output=True,text=True).stdout.strip()
json.dump({'_note':'Frozen output of benchmarks/racket_fidelity/oracle.rkt against tests/fixtures/racket/*.rkt. Regenerate with tests/fixtures/racket/REGENERATE.md when a fixture changes.','racket_version':ver,'files':out},
          open('tests/fixtures/racket_oracle.json','w'), indent=2, sort_keys=True)
"
```

## `tests/fixtures/racket_reader_oracle.json`

The second frozen file is the output of Racket's own **reader** against the
same fixtures — every syntax object `read-syntax` produces, with its byte
span — and gates `tests/test_racket_reader.py` the same way. Regenerate it
together with the first whenever a fixture changes:

```bash
racket benchmarks/racket_fidelity/reader_oracle.rkt tests/fixtures/racket/*.rkt \
  | python3 -c "
import json,sys,os,subprocess
out={}
for line in sys.stdin:
    line=line.strip()
    if line.startswith('{'):
        rec=json.loads(line); rec['file']=os.path.basename(rec['file']); out[rec['file']]=rec
ver=subprocess.run(['racket','--version'],capture_output=True,text=True).stdout.strip()
json.dump({'_note':'Frozen output of benchmarks/racket_fidelity/reader_oracle.rkt against tests/fixtures/racket/*.rkt: every syntax object Racket\'s own reader produces, as [type, 1-based byte position, byte span, at-form?]. Regenerate with tests/fixtures/racket/REGENERATE.md when a fixture changes.','racket_version':ver,'files':out},
          open('tests/fixtures/racket_reader_oracle.json','w'), indent=None, separators=(',',':'), sort_keys=True)
"
```

⚠ Regenerating is not a way to make a red test green. If the frozen data stops
matching, the extractor changed what it claims about real code — read the diff
before touching this file.
