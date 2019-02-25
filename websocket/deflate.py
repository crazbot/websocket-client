#
# copyright all reserved by Harrse
#

from ._exceptions import *
import pyflate

class MFile(object):
    raw = None
    i = 0
    len = 0
    def __init__(self, data):
        self.raw = data
        self.i = 0
        self.len = len(data)
    def eof(self):
        if self.i>=self.len:
            return True
        return False
    def read(self, n):
        i = self.i
        if self.len-i >= n:
            self.i += n
            return self.raw[i:i+n]
        return None

def gzip(data_in):
    f = MFile(data_in)
    field = pyflate.RBitfield(f)
    b = pyflate.Bitfield(field)
    out = []
    while True:
        lastbit = b.readbits(1)
        blocktype = b.readbits(2)
        if f.eof():
            break
        if blocktype == 0:
            b.align()
            length = b.readbits(16)
            if length & b.readbits(16):
                raise WebSocketPayloadException("stored block lengths do not match each other")
            for i in range(length):
                out.append(chr(b.readbits(8)))
        elif blocktype == 1 or blocktype == 2: # Huffman
            main_literals, main_distances = None, None

            if blocktype == 1: # Static Huffman
                static_huffman_bootstrap = [(0, 8), (144, 9), (256, 7), (280, 8), (288, -1)]
                static_huffman_lengths_bootstrap = [(0, 5), (32, -1)]
                main_literals = pyflate.HuffmanTable(static_huffman_bootstrap)
                main_distances = pyflate.HuffmanTable(static_huffman_lengths_bootstrap)

            elif blocktype == 2: # Dynamic Huffman
                literals = b.readbits(5) + 257
                distances = b.readbits(5) + 1
                code_lengths_length = b.readbits(4) + 4

                l = [0] * 19
                for i in range(code_lengths_length):
                    l[pyflate.code_length_orders(i)] = b.readbits(3)

                dynamic_codes = pyflate.OrderedHuffmanTable(l)
                dynamic_codes.populate_huffman_symbols()
                dynamic_codes.min_max_bits()

                code_lengths = []
                n = 0
                while n < (literals + distances):
                    r = dynamic_codes.find_next_symbol(b)
                    if 0 <= r <= 15: # literal bitlength for this code
                        count = 1
                        what = r
                    elif r == 16: # repeat last code
                        count = 3 + b.readbits(2)
                        what = code_lengths[-1]
                    elif r == 17: # repeat zero
                        count = 3 + b.readbits(3)
                        what = 0
                    elif r == 18: # repeat zero lots
                        count = 11 + b.readbits(7)
                        what = 0
                    else:
                        raise WebSocketPayloadException("next code length is outside of the range 0 <= r <= 18")
                    code_lengths += [what] * count
                    n += count
                main_literals = pyflate.OrderedHuffmanTable(code_lengths[:literals])
                main_distances = pyflate.OrderedHuffmanTable(code_lengths[literals:])
            main_literals.populate_huffman_symbols()
            main_distances.populate_huffman_symbols()
            main_literals.min_max_bits()
            main_distances.min_max_bits()
            literal_count = 0
            while True:
                r = main_literals.find_next_symbol(b)
                if 0 <= r <= 255:
                    literal_count += 1
                    out.append(chr(r))
                elif r == 256:
                    if literal_count > 0:
                        literal_count = 0
                    break
                elif 257 <= r <= 285: # dictionary lookup
                    if literal_count > 0:
                        literal_count = 0
                    length_extra = b.readbits(pyflate.extra_length_bits(r))
                    length = pyflate.length_base(r) + length_extra
                    
                    r1 = main_distances.find_next_symbol(b)
                    if 0 <= r1 <= 29:
                        distance = pyflate.distance_base(r1) + b.readbits(pyflate.extra_distance_bits(r1))
                        while length > distance:
                            out += out[-distance:]
                            length -= distance
                        if length == distance:
                            out += out[-distance:]
                        else:
                            out += out[-distance:length-distance]
                    elif 30 <= r1 <= 31:
                        raise WebSocketPayloadException("illegal unused distance symbol in use @" + `b.tell()`)
                elif 286 <= r <= 287:
                    raise WebSocketPayloadException("illegal unused literal/length symbol in use @" + `b.tell()`)
        elif blocktype == 3:
            raise WebSocketPayloadException("illegal unused blocktype in use @" + `b.tell()`)

        if lastbit:
            break

    return "".join(out)
