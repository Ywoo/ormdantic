from typing import (
    Any, ForwardRef, Tuple, Dict, Type, Generic, TypeVar, Iterator, Callable, Optional,
    List, ClassVar, cast 
)
import datetime
import inspect
import functools
from uuid import uuid4

import orjson

from pydantic import (
    BaseModel, ConstrainedDecimal, ConstrainedInt, Field, ConstrainedStr, PrivateAttr,
)

from ormdantic.util.hints import is_derived_or_collection_of_derived

from ..util import (
    get_logger,
    get_base_generic_type_of, get_type_args, update_forward_refs_in_generic_base,
    is_derived_from, resolve_forward_ref, is_list_or_tuple_of,
    resolve_forward_ref_in_args
)
from ..util.tools import convert_tuple, unique

JsonPathAndType = Tuple[Tuple[str,...], Type[Any]]
StoredFieldDefinitions = Dict[str, JsonPathAndType]
 
T = TypeVar('T')


def _orjson_dumps(v, *, default):
    # orjson.dumps returns bytes, to match standard json.dumps we need to decode
    return orjson.dumps(v, default=default).decode()

class SchemaBaseModel(BaseModel):
    class Config:
        title = 'model which can generate json schema.'

        json_dumps = _orjson_dumps
        json_loads = orjson.loads


class PersistentModel(SchemaBaseModel):
    _stored_fields: ClassVar[StoredFieldDefinitions] = {
    }
    _row_id : int = PrivateAttr(0)

    def _after_load(self):
        pass

    def _before_save(self):
        pass

    class Config:
        title = 'model which can be saved in database'



ModelT = TypeVar('ModelT', bound=SchemaBaseModel)
PersistentModelT = TypeVar('PersistentModelT', bound=PersistentModel)


_logger = get_logger(__name__)

class StoredMixin():
    ''' the json value will be saved as table fields. '''
    pass


class ReferenceMixin(Generic[ModelT], StoredMixin):
    ''' refenence key which indicate other row in other table like database's foreign key 
        ModelT will describe the type which is referenced.
    '''
    _target_field: ClassVar[str] = ''
    pass


class IdentifyingMixin(StoredMixin):
    ''' the json value will be used for identifing the object. 
    The value of this type will be update through the sql param 
    so, this field of database will not use stored feature. '''
    
    def new_if_empty(self:T) -> T:
        raise NotImplementedError('fill if exist should be implemented.')

class IndexMixin(StoredMixin):
    ''' the json value will be indexed as table fields. '''
    pass


class UniqueIndexMixin(IndexMixin):
    ''' the json value will be indexed as unique. '''
    pass


class FullTextSearchedMixin(StoredMixin):
    ''' the json value will be used by full text searching.'''
    pass


# Array Index Mixin will contain the several data which are indexed.
# where parameter use the field of this type. if the value is array,
# it should be all matched. but the value is scalar, 
# one of value of this type is matched.
class ArrayIndexMixin(IndexMixin, List[T]):
    ''' the json value will be indexed as table fields. '''
    pass 


class PartOfMixin(Generic[ModelT]):
    '''part of some json. ModelT will be container. '''
    pass


class StringIndex(ConstrainedStr, IndexMixin):
    ''' string index '''
    pass


class StringReference(ConstrainedStr, ReferenceMixin[ModelT]):
    ''' string referenece '''
    pass


class DecimalIndex(ConstrainedDecimal, IndexMixin):
    ''' decimal index'''
    pass


class IntIndex(ConstrainedInt, IndexMixin):
    ''' decimal index'''
    pass


class IntReference(ConstrainedStr, ReferenceMixin[ModelT]):
    ''' int referenece '''
    pass


class DateIndex(datetime.date, IndexMixin):
    ''' date index '''
    pass


class DateTimeIndex(datetime.datetime, IndexMixin):
    ''' date time index '''
    pass


class UniqueStringIndex(ConstrainedStr, UniqueIndexMixin):
    ''' Unique Index string '''
    pass


class IdStr(ConstrainedStr, IdentifyingMixin):
    max_length = 64 # sha256 return 64 char
    ''' UUID string'''

    def new_if_empty(self) -> 'IdStr':
        if self == '':
            return IdStr(uuid4().hex)

        return self


class FullTextSearchedStr(ConstrainedStr, FullTextSearchedMixin):
    ''' String for full text searching '''
    pass


class FullTextSearchedStringIndex(FullTextSearchedStr, IndexMixin):
    ''' string for full text searching and indexing'''
    pass


class StringArrayIndex(ArrayIndexMixin[str]):
    ''' Array of string '''
    pass


class IntegerArrayIndex(ArrayIndexMixin[int]):
    ''' Array of string '''
    pass


class IdentifiedMixin(SchemaBaseModel):
    id: IdStr = Field(default='', title='identifier for retreiving')


class IdentifiedModel(PersistentModel, IdentifiedMixin):
    ''' identified by uuid '''
    version:str = Field(default='0.1.0')

    class Config:
        title = 'base object which can be saved or retreived by id'


IdentifiedModelT = TypeVar('IdentifiedModelT', bound=IdentifiedModel)


def get_container_type(type_:Type[ModelT]) -> Optional[Type[ModelT]]:
    ''' get the type of container '''
    part_type = get_base_generic_type_of(cast(Type, type_), PartOfMixin)

    if part_type:
        return get_type_args(part_type)[0]

    return None


def get_field_names_for(type_:Type, *types:Type) -> Tuple[str,...]:
    types = convert_tuple(types)

    return tuple(field_name for field_name, _ in get_field_name_and_type(type_, *types))


def get_field_name_and_type(type_:Type, 
                            *target_types: Type,
                            ) -> Tuple[Tuple[str, Type]]:
    if not is_derived_from(type_, BaseModel):
        _logger.fatal(f'type_ {type_=}should be subclass of BaseModel. '
                      f'check the mro {inspect.getmro(type_)}')
        raise RuntimeError(f'Invalid type {type_}.')

    target_types = convert_tuple(target_types) 

    name_and_types = []

    for field_name, model_field in type_.__fields__.items():
        field_type = model_field.outer_type_ 

        if not target_types or any(is_derived_or_collection_of_derived(field_type, t) for t in target_types):
            name_and_types.append((field_name, model_field.outer_type_))

    return tuple(name_and_types)


def get_field_type(type_:Type[ModelT], field_name:str) -> type:
    if not is_derived_from(type_, BaseModel):
        _logger.fatal(f'type_ {type_=} should be the subclass of BaseModel. '
                      f'check the mro {inspect.getmro(type_)}')
        raise RuntimeError(f'Invalid type {type_}.')

    return type_.__fields__[field_name].outer_type_


def update_forward_refs(type_:Type[ModelT], localns:Dict[str, Any]):
    type_.update_forward_refs(**localns)

    # resolve outer type also,
    for model_field in type_.__fields__.values(): 
        if isinstance(model_field.outer_type_, ForwardRef):
            model_field.outer_type_ = resolve_forward_ref(model_field.outer_type_, localns)
        else:
            model_field.outer_type_ = resolve_forward_ref_in_args(model_field.outer_type_, localns)
        
    update_forward_refs_in_generic_base(type_, localns)


def is_field_list_or_tuple_of(type_:Type, field_name:str, *parameters:Type) -> bool:
    model_field = type_.__fields__[field_name]

    return is_list_or_tuple_of(model_field.outer_type_, *parameters)


def get_part_types(type_:Type) -> Tuple[Type]:
    return tuple(
        unique(
            model_field.type_
            for model_field in type_.__fields__.values()
            if is_derived_from(model_field.type_, PartOfMixin)
        )
    )
        

def get_identifer_of(model:SchemaBaseModel) -> Iterator[Tuple[str, Any]]:
    for field_name, model_field in type(model).__fields__.items(): 
        if is_derived_from(model_field.outer_type_, IdentifyingMixin):
            yield (field_name, getattr(model, field_name))


def assign_identifying_fields_if_empty(model:ModelT, inplace:bool=False) -> ModelT:
    to_be_updated  = None

    for field_name in type(model).__fields__.keys(): 
        field_value = getattr(model, field_name)

        updated_value = (
            _replace_scalar_value_if_empty_value(field_value, inplace) 
            or _replace_vector_if_empty_value(field_value, inplace)
        )

        if updated_value is not None:
            if to_be_updated is None:
                to_be_updated = model if inplace else model.copy()

            setattr(to_be_updated, field_name, updated_value)

    return to_be_updated or model


def _replace_scalar_value_if_empty_value(obj:Any, inplace:bool) -> Any:
    if isinstance(obj, IdentifyingMixin):
        new_value = obj.new_if_empty()

        if new_value is not obj:
            return new_value
    elif isinstance(obj, PartOfMixin) and isinstance(obj, SchemaBaseModel):
        replaced = assign_identifying_fields_if_empty(obj, inplace)

        if replaced is not obj:
            return replaced

    return None


def _replace_vector_if_empty_value(obj:Any, inplace:bool) -> Any:    
    if isinstance(obj, (list, tuple)):
        if not obj:
            return None

        to_be_updated = None

        for index, item in enumerate(obj):
            replaced = _replace_scalar_value_if_empty_value(item, inplace)

            if not to_be_updated and replaced is not None:
                to_be_updated = list(obj[:index])

            if to_be_updated is not None:
                to_be_updated.append(replaced)

        if isinstance(obj, tuple) and to_be_updated:
            to_be_updated = tuple(to_be_updated)

        return to_be_updated

    return None


def get_stored_fields_for(type_:Type,
                          type_or_predicate: Type[T] | Callable[[Tuple[str, ...], Type], bool]) -> Dict[str, Tuple[Tuple[str,...], Type[T]]]:
    stored = get_stored_fields(type_)

    if inspect.isfunction(type_or_predicate):
        return {
            k: (paths, cast(Type[T], type_)) for k, (paths, type_) in stored.items()
            if type_or_predicate(paths, type_)
        }
    else:
        return {
            k: (paths, cast(Type[T], type_)) for k, (paths, type_) in stored.items()
            if is_derived_from(type_, type_or_predicate) 
                or is_list_or_tuple_of(type_, type_or_predicate)
        }


def get_stored_fields(type_:Type):
    stored_fields : StoredFieldDefinitions = {
        field_name:(_get_json_paths(field_name, field_type), field_type)
        for field_name, field_type in get_field_name_and_type(type_, StoredMixin)
    }

    for fields in reversed([cast(PersistentModel, base)._stored_fields
        for base in inspect.getmro(type_) if is_derived_from(base, PersistentModel)]):
        stored_fields.update(fields)

    adjusted = {}

    for field_name, (paths, field_type) in stored_fields.items():
        is_collection_type = is_list_or_tuple_of(field_type)

        _validate_json_paths(paths)

        if is_collection_type and paths[-1] != '$' and paths[0] != '..':
            adjusted[field_name] = (paths + ('$',), field_type)

    return stored_fields | adjusted
        

def _get_json_paths(field_name, field_type) -> Tuple[str,...]:
    paths: List[str] = []

    if is_derived_from(field_type, ArrayIndexMixin):
        paths.extend([f'$.{field_name}[*]', '$'])
    else:
        paths.append(f'$.{field_name}')

    return tuple(paths)


def _validate_json_paths(paths:Tuple[str]):
    if any(not (p == '..' or p.startswith('$.') or p == '$') for p in paths):
        _logger.fatal(f'{paths} has one item which did not starts with .. or $.')
        raise RuntimeError('Invalid path expression. the path must start with $')

    # if is_collection and paths[-1] != '$':
    #     _logger.fatal(f'{paths} should end with $ for collection type')
    #     raise RuntimeError('Invalid path expression. collection type should end with $.')


