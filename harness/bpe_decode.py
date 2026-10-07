#!/usr/bin/env python3
"""Undo byte-level BPE mojibake in the DeepSeek logs (README). usage: src dst field"""
import json, sys

def bytes_to_unicode():
    bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + n); n += 1
    return dict(zip(bs, [chr(c) for c in cs]))

U2B = {v: k for k, v in bytes_to_unicode().items()}

def decode(s):
    out = bytearray()
    for c in s:
        if c in U2B:
            out.append(U2B[c])
        else:
            out.extend(c.encode("utf-8"))
    return out.decode("utf-8", errors="replace")

if __name__ == "__main__":
    src, dst, field = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(dst, "w") as out:
        for line in open(src):
            r = json.loads(line)
            r[field] = decode(r[field])
            out.write(json.dumps(r) + "\n")
