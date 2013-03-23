import mmap
import struct

import srddl.core.helpers as sch

from srddl.core.fields import BoundValue
from srddl.core.offset import Offset

class Data:
    def __init__(self, buf, ro=False):
        self.buf, self.ro, self._mapped = buf, ro, dict()

        # Probably not foolproof...
        try: self.buf[0] = self.buf[0]
        except: self.ro = True

    def __del__(self):
        self.close()

    def mapped(self, offset, fltr=None):
        offset = Offset(offset)
        res = [x for x in self._mapped[offset] if fltr is None or fltr(x)]
        if len(res) == 1:
            return res[0]
        raise Exception('fiiiiiiiiii')

    def map(self, offset, struct):
        offset = Offset(offset)
        s = struct(self, offset)
        self._mapped[offset] = self._mapped.get(offset, []) + [s]
        s._setup(self)
        return s

    def map_array(self, offset, nb, struct):
        offset = Offset(offset)
        for _ in range(nb):
            offset += self.map(offset, struct)['size']

    def unpack_from(self, frmt, offset):
        return struct.unpack_from(frmt, self.buf, offset)

    def pack_into(self, frmt, offset, *args):
        if self.ro:
            raise Exception('fu')
        struct.pack_into(frmt, self.buf, offset, *args)

    def close(self):
        pass


class FileData(Data):
    Mode = sch.enum(
        RDONLY=('rb', mmap.PROT_READ),
        RDWR=('r+b', mmap.PROT_READ | mmap.PROT_WRITE),
    )

    def __init__(self, filename, mode=Mode.RDONLY):
        self.f = open(filename, mode[0])
        super().__init__(mmap.mmap(self.f.fileno(), 0, prot=mode[1]))

    def close(self):
        self.buf.close()
        self.f.close()