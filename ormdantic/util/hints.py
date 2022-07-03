from typing import (
    get_args, Type, get_origin, Tuple, Any, Generic, Protocol,
    ForwardRef, Dict, Generic, _collect_type_vars
)
from inspect import getmro
import sys
import copy

from .tools import convert_tuple


def get_base_generic_type_of(type_:Type, generic_types:Type | Tuple[Type,...]) -> Type | None:
    generic_types = convert_tuple(generic_types)

    for base_type in get_mro_with_generic(type_):
        if any(base_type is t or get_origin(base_type) is t for t in generic_types):
            return base_type

    return None


def get_type_args(type_:Type) -> Tuple[Any,...]:
    return get_args(type_)


# from https://github.com/python/typing/issues/777
def _generic_mro(result, tp):
    origin = get_origin(tp)
    origin = origin or tp

    result[origin] = tp
    if hasattr(origin, "__orig_bases__"):
        parameters = _collect_type_vars(origin.__orig_bases__)
        substitution = dict(zip(parameters, get_args(tp)))

        for base in origin.__orig_bases__:
            if get_origin(base) in result:
                continue
            base_parameters = getattr(base, "__parameters__", ())
            if base_parameters:
                base = base[tuple(substitution.get(p, p) for p in base_parameters)]
            _generic_mro(result, base)


def get_mro_with_generic(tp:Type):
    origin = get_origin(tp)

    if origin is None and not hasattr(tp, "__orig_bases__"):
        if not isinstance(tp, type):
            raise TypeError(f"{tp!r} is not a type or a generic alias")
        return tp.__mro__
    # sentinel value to avoid to subscript Generic and Protocol

    result = {Generic: Generic, Protocol: Protocol}
    _generic_mro(result, tp)
    cls = origin if origin is not None else tp
    return tuple(result.get(sub_cls, sub_cls) for sub_cls in cls.__mro__)


def update_forward_refs_in_generic_base(type_:Type, localns:Dict[str, Any]):
    # convert ForwardRef as resolved class in __orig_bases__ in base classes
    # if class is derived from generic, it has __orig_bases__ attribute

    if hasattr(type_, '__orig_bases__'):
        type_.__orig_bases__ = tuple(
            _resolve_base_or_args(base, localns) for base in type_.__orig_bases__)

                
def _resolve_base_or_args(base:Type, localns:Dict[str, Any]) -> Type:
    if is_derived_from(base, Generic) and any(type(arg) is ForwardRef for arg in base.__args__):
        new_type = copy.copy(base)
        new_type.__args__ = tuple(resolve_forward_ref(arg, localns) for arg in base.__args__)

        return new_type

    return base


def resolve_forward_ref(type_:Type, localns:Dict[str, Any]) -> Type:
    if type_.__class__ is ForwardRef:
        globalns = (
            sys.modules[type_.__module__].__dict__.copy() 
            if type_.__module__ in sys.modules else {}
        )

        real_type = type_._evaluate(globalns, localns, set())
    
        return real_type

    return type_


def is_derived_from(type_:Type, base_type:Type) -> bool:
    # if first argument is not class, the issubclass throw the exception.
    # but usually, we don't need the exception. 
    # we just want to know whether the type is derived or not.

    # if type_ is generic, we will use __origin__
    #
    # https://stackoverflow.com/questions/49171189/whats-the-correct-way-to-check-if-an-object-is-a-typing-generic
    if hasattr(type_, "__origin__"):
        type_ = get_origin(type_)

    return any(t is base_type for t in getmro(type_))


def is_collection_type_of(type_:Type, parameters:Tuple[Type,...] | Type = tuple()) -> bool:
    generic = get_base_generic_type_of(type_, (tuple, list))

    if generic:
        parameters = convert_tuple(parameters)

        if not parameters:
            return True

        args = get_args(generic) 

        # handle Tuple[str, str]
        if len(args) > 1 and len(set(args)) == 1:
            args = (args[0],)
        else:
            # handle Tuple[str, ...]
            if args[-1] is Ellipsis:
                args = args[:-1]

        return args == parameters

    return False
            
