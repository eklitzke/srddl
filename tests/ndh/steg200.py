# PYTHONPATH="." python -i tests/ndh/steg200.py ~/ctf/ndh/2013/steg200/stream

import sys

import srddl.models as sm
import srddl.fields as sf

class UnknownChunk(sm.Struct):
    pad = sf.Padding(1)
    length = sf.IntField(size=sf.Field_Sizes.INT32)
    data = sf.ByteArrayField(size=length)

class UnknownFile(sm.Struct):
    pad = sf.Padding(1)
    length = sf.IntField(size=sf.Field_Sizes.INT32)
    chunks = sf.Array(length, sf.SuperField(UnknownChunk))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: {} [stream_file]')

    with open(sys.argv[1], 'rb') as f:
        data = f.read()

    s = UnknownFile(data, 0)
