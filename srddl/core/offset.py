# srddl/core/offset.py - Helps describe offsets and sizes.
# Author: Franck Michea <franck.michea@gmail.com>
# License: New BSD License (See LICENSE)

import functools
import abc


@functools.total_ordering
class _Offset(metaclass=abc.ABCMeta):
    def __init__(self, byte=0, bit=0):
        from srddl.core.fields import BoundValue
        if isinstance(byte, BoundValue):
            self.byte, self.bit = byte['value'], bit
        elif isinstance(byte, _Offset):
            self.byte, self.bit = byte.byte, byte.bit
        else:
            self.byte, self.bit = byte, bit
        self.byte, self.bit = self.byte + self.bit // 8, self.bit % 8

    def __index__(self):
        return self.byte

    def __repr__(self):
        return '<{} at {:#x} with value ({}, {})>'.format(
            self.__class__.__name__, id(self), self.byte, self.bit
        )

    def __str__(self):
        res = '{} byte'.format(self.byte)
        if 1 < self.byte:
            res += 's'
        if self.bit:
            res += ' {} bit'.format(self.bit)
            if 1 < self.bit:
                res += 's'
        return res

    def __hash__(self):
        return hash('{}::{}'.format(self.byte, self.bit))

    def __eq__(self, other):
        # This function is needed by functools.total_ordering.
        if isinstance(other, _Offset):
            return (self.byte, self.bit) == (other.byte, other.bit)
        return (self.byte, self.bit) == (other, 0)

    def __lt__(self, other):
        # This function is needed by functools.total_ordering.
        if isinstance(other, _Offset):
            return (self.byte, self.bit) < (other.byte, other.bit)
        return (self.byte, self.bit) < (other, 0)

    def __add__(self, other):
        if isinstance(other, _Offset):
            bit = self.bit + other.bit
            byte = self.byte + other.byte + (bit >> 3)
            bit &= 0b111
            return self.__class__(byte=byte, bit=bit)
        return self.__class__(byte=(self.byte + other), bit=self.bit)

    def __radd__(self, other):
        return self + self.__class__(byte=other)

    def __sub__(self, other):
        if isinstance(other, _Offset):
            bit = self.bit - other.bit
            byte = self.byte - other.byte
            if bit < 0:
                bit = 8 + bit
                byte -= 1
            return self.__class__(byte=byte, bit=bit)
        return self.__class__(byte=(self.byte - other), bit=self.bit)

    def __rsub__(self, other):
        return self.__class__(byte=(other - self.byte), bit=self.bit)

    def aligned(self):
        return (self.bit == 0)

    @abc.abstractmethod
    def rounded(self):
        pass


class Offset(_Offset):
    def rounded(self):
        return self.byte


class Size(_Offset):
    def rounded(self):
        return self.byte + (1 if self.bit else 0)
