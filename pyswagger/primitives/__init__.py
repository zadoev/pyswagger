from __future__ import absolute_import
from ..utils import deref, CycleGuard
from ._int import create_int, validate_int
from ._str import create_str, validate_str
from ._bool import create_bool
from ._byte import Byte
from ._time import Date, Datetime
from ._file import File
from ._float import create_float, validate_float
from ._array import Array
from ._model import Model
from .comm import create_obj, _2nd_pass_obj
import functools
import json


class SwaggerPrimitive(object):
    """ primitive factory
    """
    def __init__(self):
        from ._model import Model
        from ._array import Array

        self._map = {
            # int
            'integer': {
                'int32': (create_int, validate_int),
                'int64': (create_int, validate_int),
            },

            # float
            'number':{
                'float': (create_float, validate_float),
                'double': (create_float, validate_float),
            },

            # str
            'string': {
                '': (create_str, validate_str),
                None: (create_str, validate_str),

                # TODO: add validation for email, uuid
                # TODO: add convertion of uuid from python's one
                'email': (create_str, validate_str),
                'uuid': (create_str, validate_str),

                'byte': (functools.partial(create_obj, constructor=Byte), _2nd_pass_obj),
                'date': (functools.partial(create_obj, constructor=Date), _2nd_pass_obj),
                'date-time': (functools.partial(create_obj, constructor=Datetime), _2nd_pass_obj),
            },

            # bool
            'boolean': {
                '': (create_bool, None),
                None: (create_bool, None),
            },

            # file
            'file': {
                '': (functools.partial(create_obj, constructor=File), _2nd_pass_obj),
                None: (functools.partial(create_obj, constructor=File), _2nd_pass_obj),
            },

            # array
            'array': {
                '': (functools.partial(create_obj, constructor=Array), _2nd_pass_obj),
                None: (functools.partial(create_obj, constructor=Array), _2nd_pass_obj),
            },

            # model / schema Object
            'object': {
                '': (functools.partial(create_obj, constructor=Model), _2nd_pass_obj),
                None: (functools.partial(create_obj, constructor=Model), _2nd_pass_obj),
            }
        }

    def get(self, _type, _format=None):
        r = self._map.get(_type, None)
        return (None, None) if r == None else r.get(_format, (None, None))

    def set(self, _type, creater, _format=None, _2nd_pass=None):
        # TODO: implement it
        pass

    def produce(self, obj, val, ctx=None):
        """ factory function to create primitives

        :param pyswagger.spec.v2_0.objects.Schema obj: spec to construct primitives
        :param val: value to construct primitives

        :return: the created primitive
        """
        val = obj.default if val == None else val
        if val == None:
            return None

        cleanup = ctx == None # it's the top-most call in recursive
        obj = deref(obj)
        ctx = {} if ctx == None else ctx
        if 'name' not in ctx and hasattr(obj, 'name'):
            ctx['name'] = obj.name
        if 'guard' not in ctx:
            ctx['guard'] = CycleGuard()
        if 'addp_schema' not in ctx:
            # Schema Object of additionalProperties
            ctx['addp_schema'] = None
        if 'addp' not in ctx:
            # additionalProperties
            ctx['addp'] = False
        if '2nd_pass' not in ctx:
            # 2nd pass processing function
            ctx['2nd_pass'] = None
        if 'factory' not in ctx:
            # primitive factory
            ctx['factory'] = self

        # cycle guard
        ctx['guard'].update(obj)

        ret = None
        if obj.type:
            creater, _2nd = self.get(_type=obj.type, _format=obj.format)
            if not creater:
                raise ValueError('Can\'t resolve type from:(' + str(obj.type) + ', ' + str(obj.format) + ')')

            ret = creater(obj, val, ctx)
            if _2nd:
                val = _2nd(obj, ret, val, ctx)
                ctx['2nd_pass'] = _2nd
        elif len(obj.properties) or obj.additionalProperties:
            ret = Model()
            val = ret.apply_with(obj, val, ctx)

        if isinstance(ret, (Date, Datetime, Byte, File)):
            # it's meanless to handle allOf for these types.
            return ret

        def _apply(o, r, v, c):
            if hasattr(ret, 'apply_with'):
                v = r.apply_with(o, v, c)
            else:
                _2nd = c['2nd_pass']
                if _2nd == None:
                    _, _2nd = self.get(_type=o.type, _format=o.format)
                if _2nd:
                    _2nd(o, r, v, c)
                    # update it back to context
                    c['2nd_pass'] = _2nd
            return v

        # handle allOf for Schema Object
        allOf = getattr(obj, 'allOf', None)
        if allOf:
            not_applied = []
            for a in allOf:
                a = deref(a)
                if not ret:
                    # try to find right type for this primitive.
                    ret = self.produce(a, val, ctx)
                    is_member = hasattr(ret, 'apply_with')
                else:
                    val = _apply(a, ret, val, ctx)

                if not ret:
                    # if we still can't determine the type,
                    # keep this Schema object for later use.
                    not_applied.append(a)
            if ret:
                for a in not_applied:
                    val = _apply(a, ret, val, ctx)

        if ret and cleanup and hasattr(ret, 'cleanup'):
            val = ret.cleanup(val, ctx)

        return ret

    def is_primitive(self, _type):
        """ check if a given object refering to a primitive
        defined in spec.

        :param dict obj: object to be checked
        :return: True if this object is a primitive.
        """
        return _type in self._map.keys()
