# Author: Franck Michea <franck.michea@gmail.com>
# License: New BSD License (See LICENSE)

import abc
import binascii
import functools
import inspect
import pprint

import srddl.core.helpers as sch
import srddl.core.nameddict as scnd
import srddl.exceptions as se
import srddl.helpers as sh

from srddl.core.signals import Signal
from srddl.core.offset import Offset, Size

FieldInitStatus = sch.enum(KO=0, INIT=1, OK=2)

class _MetaAbstractMappedValue(scnd._MetaNamedDict, sch.MetaAbstractDescriptor):
    pass

class _MetaAbstractField(_MetaAbstractMappedValue):
    '''
    This meta-class will make sure that initialization of a Field is done
    correctly. To do so, it will wrap some methods of a class with its own
    functions and do some checks for the field.
    '''

    def __new__(cls, clsname, bases, kwds):
        # When referencing a field from another, we basically need to know if
        # the field is initialized or not, so if we can fetch its value or not.
        initialize = kwds.get('initialize')
        if initialize is not None:
            @functools.wraps(initialize)
            def wrapper(self, instance, offset, **kwargs):
                # There are three states to the initialization process:
                #
                #   FieldInitStatus.KO, FieldInitStatus.INIT, FieldInitStatus.OK
                #
                # When the value is not present, this means we haven't even
                # begun to initialize the field. When False, the initialization
                # process has begun, and finally when True everything is fine.
                #
                # Since we want inheritance to work, we need to set the status
                # only on the call on a instance that is the first one.
                try:
                    status = self._get_data(instance, 'status')
                except se.NoFieldDataError:
                    status = FieldInitStatus.KO
                self._set_data(instance, 'status', FieldInitStatus.INIT)

                if status != FieldInitStatus.INIT:
                    self._set_data(instance, 'status', FieldInitStatus.OK)
            kwds['initialize'] = wrapper

        __get__ = kwds.get('__get__')
        if __get__ is not None:
            @functools.wraps(__get__)
            @functools.lru_cache()
            def wrapper(self, instance, owner=None):
                if self._get_data(instance, 'status') != FieldInitStatus.OK:
                    raise se.FieldNotReadyError(self)
                res = __get__(self, instance, owner=owner)
                from srddl.models import Struct
                if not (res is None or isinstance(res, (BoundValue, Struct))):
                    raise se.NotABoundValueError(self)
                return res
            kwds['__get__'] = wrapper

        for func_name in ['decode']:
            func = kwds.get(func_name)
            if func is not None:
                @functools.wraps(func)
                @functools.lru_cache()
                def wrapper(*args, **kwargs):
                    return func(*args, **kwargs)
                kwds[func_name] = wrapper
        return super().__new__(cls, clsname, bases, kwds)


class Value(scnd.NamedDict):
    '''
    The Value class is used by the ``values`` keyword parameter of certain
    fields. It is used to define documentation on possibe values. The usage of
    this values is dependent on the actual field, see their respective
    documentation.
    '''

    class Meta:
        init_props = ['value', 'name', 'description']

    @scnd.abstractproperty()
    def _value(self, flags):
        '''
        This is the actual value in a builtin type, like an int or a bytearray.
        Most fields will compare this value to the data unpacked to decide if
        the data is indeed described by this Value.
        '''
        pass

    @scnd.property()
    def _name(self, flags):
        '''
        This is the short name for the Value. It usually is the name of a
        constant, like a define as would be found in a C header.
        '''
        pass

    @scnd.property()
    def _description(self, flags):
        '''This property holds a long description of the field.'''
        pass

    @scnd.property(flags=['verbose'])
    def _display_value(self, flags):
        '''
        This property returns a comprehensible string describing the value.
        '''
        res = str(self['value'])
        if self['name'] is not None:
            res = '{}'.format(self['name'])
            if flags['verbose']:
                res = '{} ({})'.format(self['value'], res)
        return res


class AbstractMappedValue(Value, metaclass=_MetaAbstractMappedValue):
    '''
    This class holds the different properties shared by anything that is mapped
    (like strutures or fields). Any mappable value should inherit at least from
    this class and implement the different abstract properties it declares.
    '''

    class Meta(Value.Meta):
        init_props = ['offset'] + Value.Meta.init_props

    def _extract_raw(self, data):
        # Unpack the complete data.
        f = '{}s'.format(self['size'].rounded())
        d = bytearray(data.unpack_from(f, self['offset'].rounded())[0])
        # Remove starting bits not included in the mapped value.
        d[0] = d[0] & ((0xff >> self['offset'].bit) & 0xff)
        # Remove trailing bits not included in the mapped value.
        s = self['size'].bit + (self['offset'].bit if not self['size'].byte else 0)
        d[-1] = d[-1] & ((0xff << (8 - s if s else 0)) & 0xff)
        return d

    def _hexify(self, data):
        return binascii.hexlify(self._extract_raw(data))

    @scnd.abstractproperty()
    def _offset(self, flags):
        '''The offset where the mapped value starts in the data.'''
        pass

    @scnd.abstractproperty(flags=['static'])
    def _size(self, flags):
        '''
        The size of the mapped value as a :class:`srddl.core.offset.Size`
        instance.
        '''
        pass

    @scnd.abstractproperty()
    def _hex(self, flags):
        '''
        This property represents the data as an hexadecimal string that is the
        the data under the mapped value. It is the size of the mapped value
        rounded to the upper byte if the value is not aligned.
        '''
        pass

    @scnd.abstractproperty()
    def _raw(self, flags):
        '''
        This property represents the raw data of the complete mapped value. It
        is a bytearray, with a size rounded to the upper byte of the size of the
        mapped value.
        '''
        pass


@functools.total_ordering
class BoundValue(AbstractMappedValue):
    '''
    The BoundValue class represents a value obtained by fetching a Field. Each
    field may define and return a specialized version of the BoundValue,
    defining properties for more advanced usage of these values.

    If a Value was found, it is copied over the BoundValue, so you can retreive
    the documentation associated with the Value (during Field definition)
    directly with the BoundValue.

    Aside from this, the BoundValue also exposes the size of the value (in
    bytes) and its offset. You may not need these value, but they are public
    anyway.
    '''

    class Meta(AbstractMappedValue.Meta):
        init_props = ['_', 'field'] + AbstractMappedValue.Meta.init_props

    def __init__(self, instance, field, offset, valid):
        super().__init__(field, offset)
        self._instance, self._valid_func = instance, valid

    def __getitem__(self, item):
        if item != 'value' and item in Value.__nd_props__:
            # Force decoding of value for those fields.
            _ = self['value']
        return super().__getitem__(item)

    def _raw(self, flags):
        return self._extract_raw(self._instance['data'])

    def _hex(self, flags):
        return self._hexify(self._instance['data'])

    def _size(self, flags):
        return Size(byte=sch.reference_value(self._instance, self._field._size))

    def _value(self, flags):
        res = self._field.decode(self._instance, self['offset'])
        if isinstance(res, Value):
            self.copy(res)
            return res['value']
        return res

    def _valid(self, flags):
        return self._valid_func(self['value'])

    def _display_value(self, flags):
        res = self._field._display_value(flags, self['value'])
        if res is not None and self['name'] is not None:
            res += ' ({})'.format(self['name'])
        elif res is None:
            if self['value'] is not None:
                if self['name'] is not None:
                    res = super()[flags['_nd_attrname']]
                else:
                    res = str(self['value'])
            else:
                res = '[...]'
        return res

    @scnd.abstractproperty()
    def _field(self, flags):
        pass

    def __bool__(self):
        return bool(self['value'])

    def __eq__(self, other):
        # This function is needed by functools.total_ordering.
        if isinstance(other, BoundValue):
            return self['value'] == other['value']
        return self['value'] == other

    def __lt__(self, other):
        # This function is needed by functools.total_ordering.
        if isinstance(other, BoundValue):
            return self.value < other.value
        return self.value < other

    def set(self, value):
        self._field.encode(self._instance, self['offset'], value)


class AbstractField(scnd.NamedDict):
    class MetaBase(scnd.NamedDict.MetaBase):
        aligned = True
        boundvalue_class = BoundValue

    class Meta:
        init_fields = ['description']

    def __init__(self, *args, **kwargs):
        self._valid = kwargs.pop('valid', lambda _: None)
        super().__init__(*args, **kwargs)

    def pre_initialize(self, instance):
        return None

    def initialize(self, instance, offset, path=None):
        if self.metaconf('aligned') and not offset.aligned():
            raise se.FieldAlignmentError()
        args = [instance, self, offset, self._valid]
        bv = self.metaconf('boundvalue_class')(*args)
        if path is not None:
            self._path = path
        self._set_data(instance, 'boundvalue', bv)
        return bv['size']

    @scnd.property()
    def _description(self, flags):
        pass

    @scnd.property()
    def _path(self, flags):
        pass

    @functools.lru_cache()
    def __get__(self, instance, owner=None):
        return self._get_data(instance, 'boundvalue')

    def __set__(self, instance, value):
        '''This function must set the new value of the field.'''
        bv = self.__get__(instance)
        offset = instance['offset'] + bv['offset']
        self.encode(instance, offset, value)

    @abc.abstractmethod
    def decode(self, instance, offset):
        pass

    @abc.abstractmethod
    def encode(self, instance, offset, value):
        pass

    def _data_key(self, name):
        return 'data-{:x}_{}'.format(id(self), name)

    def _get_data(self, instance, name):
        key = self._data_key(name)
        if key not in instance._srddl.fields_data:
            raise se.NoFieldDataError(instance, self, name)
        return instance._srddl.fields_data[key]

    def _set_data(self, instance, name, value):
        '''Sets the data associated with the field.'''
        instance._srddl.fields_data[self._data_key(name)] = value

    def _display_value(self, flags, val):
        return None
