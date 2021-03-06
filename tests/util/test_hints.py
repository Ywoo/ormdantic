from typing import ForwardRef, Generic, List, TypeVar, Tuple, get_args

import pytest

from ormdantic.util import (
    get_base_generic_type_of, get_type_args, get_mro_with_generic, 
    resolve_forward_ref, update_forward_refs_in_generic_base, is_derived_from, 
    is_list_or_tuple_of
)
from ormdantic.schema.base import PartOfMixin, PersistentModel, StringIndex
from ormdantic.util.hints import get_list_or_type_type_parameters, is_derived_or_collection_of_derived, resolve_forward_ref_in_args

T = TypeVar('T')


def test_get_base_generic_type_of():
    class GenericTest(PartOfMixin[PersistentModel]):
        pass

    base_generic = get_base_generic_type_of(GenericTest, PartOfMixin)
    assert PartOfMixin[PersistentModel] == base_generic

    base_generic = get_base_generic_type_of(GenericTest, PartOfMixin[PersistentModel])
    assert PartOfMixin[PersistentModel] == base_generic

    assert get_type_args(base_generic)[0]

    class MultipleInheritanceTest(List[str], GenericTest):
        pass

    base_generic = get_base_generic_type_of(MultipleInheritanceTest, PartOfMixin)

    assert PartOfMixin[PersistentModel] == base_generic

    base_generic = get_base_generic_type_of(MultipleInheritanceTest, list)

    assert List[str] == base_generic


def test_get_mro_with_generic():
    class Item(Generic[T]):
        pass

    class Items(Item[str]):
        pass

    assert [Items, Item[str], Generic, object] == list(get_mro_with_generic(Items))

    with pytest.raises(TypeError):
        get_mro_with_generic(0)


def test_update_forward_refs_in_generic_base():
    class Item():
        pass

    class Base(Generic[T]):
        pass

    class Derived(Base['Item']):
        pass

    update_forward_refs_in_generic_base(Derived, locals())

    base_type = get_base_generic_type_of(Derived, Base)

    assert (Item,) == get_type_args(base_type)

def test_update_forward_refs_in_args():
    V = TypeVar('V')
    class Derived(Generic[T, V]):
        pass

    class HasForwardRefInArgs(Derived['Forward', 'Forward']):
        pass

    class Forward:
        pass

    origin = getattr(HasForwardRefInArgs, '__orig_bases__')

    assert origin

    new_type = resolve_forward_ref_in_args(origin[0], locals())

    assert get_args(new_type) == (Forward, Forward)


def test_resolve_forward_ref():
    class Item():
        pass

    assert Item == resolve_forward_ref(ForwardRef("Item"), locals())
    assert Item == resolve_forward_ref(Item, locals())
    

def test_is_derived_from():
    class Item():
        pass

    class Base(Generic[T]):
        pass

    class Derived(Base['Item']):
        pass


    assert is_derived_from(Item, Item)
    assert not is_derived_from(str, Item)

    assert is_derived_from(Derived, Base)
    assert not is_derived_from(Base, Derived)

    assert not is_derived_from(Item | None, Item)


def test_is_collection_type_of():
    assert is_list_or_tuple_of(List[str], str)
    assert is_list_or_tuple_of(List[str])
    assert is_list_or_tuple_of(List)
    assert is_list_or_tuple_of(List[StringIndex], str)

    assert is_list_or_tuple_of(Tuple[str], str)
    assert is_list_or_tuple_of(Tuple[str, str], str)
    assert is_list_or_tuple_of(Tuple[str, ...], str)
    assert is_list_or_tuple_of(Tuple[str, int], str, int)

    assert not is_list_or_tuple_of(List, int)
    assert not is_list_or_tuple_of(List[str], int)
    assert not is_list_or_tuple_of(List[str], StringIndex)
    assert not is_list_or_tuple_of(int, int)


def test_get_collection_type_parameters():
    assert get_list_or_type_type_parameters(int) is None
    assert get_list_or_type_type_parameters(str) is None

    assert get_list_or_type_type_parameters(list) == tuple()
    assert get_list_or_type_type_parameters(List[str]) == (str,)
    assert get_list_or_type_type_parameters(Tuple[str, ...]) == (str,)
    assert get_list_or_type_type_parameters(Tuple[str, str]) == (str,)
    assert get_list_or_type_type_parameters(Tuple[str, str, int]) == (str, str, int)


def test_is_derived_or_collection_of_derived():
    class Item():
        pass

    class Base(Generic[T]):
        pass

    class Derived(Base['Item']):
        pass

    assert is_derived_or_collection_of_derived(Derived, Base)
    assert is_derived_or_collection_of_derived(List[Derived], Base)
    assert is_derived_or_collection_of_derived(List[Derived], Derived)
    assert not is_derived_or_collection_of_derived(List[Derived], Item)