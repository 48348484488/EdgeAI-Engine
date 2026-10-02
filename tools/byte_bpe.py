"""Small deterministic byte-level BPE. Lossless; no Unicode normalization.

Five fixed byte categories, no merges across runs or newlines. A model has all
256 byte tokens, 0..N learned merges with IDs 256.., then a BOS token. Training
must receive ONLY training documents. This is not a GPT tokenizer replica.
"""
from collections import Counter
from functools import lru_cache
import hashlib
import json
import re
from pathlib import Path

PIECES = re.compile(rb'[A-Za-z_]+|[0-9]+|[ \t]+|[\r\n]|[^A-Za-z_0-9 \t\r\n]+')
MAX_VOCAB=4096
MAX_PIECE_BYTES=64

def _merge(ids,a,b,new):
    out=[];i=0
    while i<len(ids):
        if i+1<len(ids) and ids[i]==a and ids[i+1]==b:
            out.append(new);i+=2
        else:out.append(ids[i]);i+=1
    return tuple(out)

class ByteBPE:
    def __init__(self,merges=(),instruction=False):
        if type(instruction) is not bool:raise TypeError('instruction must be bool')
        self.instruction=instruction
        if len(merges)>MAX_VOCAB-(259 if instruction else 257):raise ValueError('too many merges')
        self.merges=tuple(tuple(p) for p in merges)
        vocab=[bytes([i]) for i in range(256)];ranks={};known=set(vocab)
        for rank,p in enumerate(self.merges):
            new=256+rank
            if len(p)!=2 or any(type(x) is not int or x<0 or x>=new for x in p):
                raise ValueError('invalid merge dependency')
            a,b=p;piece=vocab[a]+vocab[b]
            if p in ranks or piece in known or len(piece)>MAX_PIECE_BYTES:
                raise ValueError('duplicate or oversized piece')
            if PIECES.findall(piece)!=[piece] or b'\n' in piece or b'\r' in piece:
                raise ValueError('merge crosses pretoken boundary')
            ranks[p]=new;vocab.append(piece);known.add(piece)
        self.vocab=tuple(vocab);self.ranks=ranks
        # Bounded cache for immutable pre-token pieces. Not part of model state.
        self._cached=lru_cache(maxsize=32768)(self._encode_piece)
    @property
    def bos_id(self):return len(self.vocab)
    @property
    def vocab_size(self):return len(self.vocab)+(3 if self.instruction else 1)
    @property
    def response_id(self):
        if not self.instruction:raise ValueError('tokenizer has no RESPONSE')
        return self.bos_id+1
    @property
    def eos_id(self):
        if not self.instruction:raise ValueError('tokenizer has no EOS')
        return self.bos_id+2
    def encode_prompt(self,raw):
        ids=self.encode(raw,add_bos=True)
        if self.instruction:ids.append(self.response_id)
        return ids
    def _encode_piece(self,piece):
        ids=tuple(piece)
        while len(ids)>1:
            choices=[(self.ranks[(a,b)],a,b) for a,b in zip(ids,ids[1:]) if (a,b) in self.ranks]
            if not choices:break
            new,a,b=min(choices);ids=_merge(ids,a,b,new)
        return ids
    def encode(self,raw,add_bos=False):
        if isinstance(raw,str):raw=raw.encode('utf-8')
        if not isinstance(raw,bytes):raise TypeError('expected bytes or str')
        if len(raw)>8*1024*1024:raise ValueError('input exceeds 8 MiB')
        out=[self.bos_id] if add_bos else []
        for p in PIECES.findall(raw):out.extend(self._cached(p))
        return out
    def decode(self,ids):
        pieces=[]
        for n in ids:
            if type(n) is not int or n<0 or n>=self.vocab_size:raise ValueError('token out of range')
            if n<self.bos_id:pieces.append(self.vocab[n])
        return b''.join(pieces)
    def payload(self):
        d={'format':'edge-byte-bpe-2' if self.instruction else 'edge-byte-bpe-1','merges':[list(p) for p in self.merges],'bos_id':self.bos_id}
        if self.instruction:d.update(response_id=self.response_id,eos_id=self.eos_id)
        return d
    def fingerprint(self):return hashlib.sha256(json.dumps(self.payload(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def save(self,path):Path(path).write_text(json.dumps(self.payload(),indent=2)+'\n',encoding='utf-8')
    @classmethod
    def load(cls,path):
        p=Path(path)
        if p.stat().st_size>1024*1024:raise ValueError('tokenizer JSON too large')
        d=json.loads(p.read_text(encoding='utf-8'))
        if d.get('format') not in ('edge-byte-bpe-1','edge-byte-bpe-2'):raise ValueError('unknown tokenizer format')
        t=cls(d['merges'],instruction=d['format']=='edge-byte-bpe-2')
        if t.instruction and (d.get('response_id')!=t.response_id or d.get('eos_id')!=t.eos_id):raise ValueError('instruction metadata mismatch')
        if d.get('bos_id')!=t.bos_id:raise ValueError('BOS metadata mismatch')
        return t
    @classmethod
    def train(cls,documents,vocab_size=513):
        if not 257<=vocab_size<=MAX_VOCAB:raise ValueError('vocabulary outside 257..4096')
        words=Counter()
        for raw in documents:
            if not isinstance(raw,bytes):raise TypeError('train on explicit bytes')
            words.update(PIECES.findall(raw))
        if not words:raise ValueError('empty corpus')
        splits={p:tuple(p) for p in words};vocab=[bytes([i]) for i in range(256)];known=set(vocab);merges=[]
        for new in range(256,vocab_size-1):
            counts=Counter()
            for p,ids in splits.items():
                for a,b in zip(ids,ids[1:]):
                    piece=vocab[a]+vocab[b]
                    if len(piece)<=MAX_PIECE_BYTES and piece not in known:counts[a,b]+=words[p]
            if not counts:break
            best=min(counts,key=lambda p:(-counts[p],p))
            if counts[best]<2:break
            a,b=best;merges.append(best);vocab.append(vocab[a]+vocab[b]);known.add(vocab[-1])
            splits={p:_merge(ids,a,b,new) for p,ids in splits.items()}
        return cls(merges)
