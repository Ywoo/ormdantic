from typing import Type, List, ClassVar
import pytest
from decimal import Decimal
from datetime import date, datetime

from pydantic import condecimal, constr, Field

from ormdantic.schema import PersistentModel
from ormdantic.database.queries import (
    get_sql_for_upserting_external_index_table, get_stored_fields, get_table_name, 
    get_sql_for_creating_table, _get_field_db_type, _generate_json_table_for_part_of,
    _build_query_and_fields_for_core_table, field_exprs,
    get_query_and_args_for_reading,
    get_sql_for_upserting_parts_table, 
    join_line, 
    _build_namespace_types, _find_join_keys, _extract_fields,
    _ENGINE, _RELEVANCE_FIELD
)
from ormdantic.schema.base import (
    IntegerArrayIndex, StringArrayIndex, FullTextSearchedStringIndex, 
    FullTextSearchedStr, PartOfMixin, StringReference, 
    UniqueStringIndex, StringIndex, DecimalIndex, IntIndex, DateIndex,
    DateTimeIndex, update_forward_refs, IdStr, 
    StoredFieldDefinitions
)

from .tools import (
    use_temp_database_cursor_with_model, 
)

ConStr200 = constr(max_length=200)
ConStr10 = constr(max_length=10)

ConDec66 = condecimal(max_digits=66)

def test_get_table_name():
    class SimpleBaseModel(PersistentModel):
        pass

    assert 'md_SimpleBaseModel' == get_table_name(SimpleBaseModel)
    assert 'md_SimpleBaseModel_part' == get_table_name(SimpleBaseModel, 'part')


def test_get_sql_for_create_table():
    class SimpleBaseModel(PersistentModel):
        pass

    assert (
        'CREATE TABLE IF NOT EXISTS `md_SimpleBaseModel` (\n'
        '  `__row_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n'
        '  `__json` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin CHECK (JSON_VALID(`__json`))\n'
        f'){_ENGINE}'
    ) == next(get_sql_for_creating_table(SimpleBaseModel))


def test_get_sql_for_create_table_with_index():
    class SampleModel(PersistentModel):
        i1: FullTextSearchedStr
        i2: FullTextSearchedStringIndex
        i3: UniqueStringIndex
        i4: StringIndex
        i5: StringArrayIndex
        i6: DecimalIndex
        i7: IntIndex
        i8: DateIndex
        i9: DateTimeIndex
        i10: IdStr

    assert (
f"""CREATE TABLE IF NOT EXISTS `md_SampleModel` (
  `__row_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `__json` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin CHECK (JSON_VALID(`__json`)),
  `i1` VARCHAR(200) AS (JSON_VALUE(`__json`, '$.i1')) STORED,
  `i2` VARCHAR(200) AS (JSON_VALUE(`__json`, '$.i2')) STORED,
  `i3` VARCHAR(200) AS (JSON_VALUE(`__json`, '$.i3')) STORED,
  `i4` VARCHAR(200) AS (JSON_VALUE(`__json`, '$.i4')) STORED,
  `i5` TEXT AS (JSON_EXTRACT(`__json`, '$.i5[*]')) STORED,
  `i6` DECIMAL(65) AS (JSON_VALUE(`__json`, '$.i6')) STORED,
  `i7` TEXT AS (JSON_VALUE(`__json`, '$.i7')) STORED,
  `i8` DATE AS (JSON_VALUE(`__json`, '$.i8')) STORED,
  `i9` DATETIME(6) AS (JSON_VALUE(`__json`, '$.i9')) STORED,
  `i10` VARCHAR(64),
  KEY `i2_index` (`i2`),
  UNIQUE KEY `i3_index` (`i3`),
  KEY `i4_index` (`i4`),
  KEY `i5_index` (`i5`),
  KEY `i6_index` (`i6`),
  KEY `i7_index` (`i7`),
  KEY `i8_index` (`i8`),
  KEY `i9_index` (`i9`),
  UNIQUE KEY `i10_index` (`i10`),
  FULLTEXT INDEX `ft_index` (`i1`,`i2`) COMMENT 'parser "TokenBigramIgnoreBlankSplitSymbolAlphaDigit"'
){_ENGINE}"""
) == next(get_sql_for_creating_table(SampleModel))


def test_get_sql_for_create_part_of_table():
    class Part(PersistentModel, PartOfMixin['Container']):
        order: StringIndex

    class Container(PersistentModel):
        parts: List[Part] = Field(default=[])

    update_forward_refs(Part, locals())
    sqls = get_sql_for_creating_table(Part)

    assert (
        'CREATE TABLE IF NOT EXISTS `md_Part_pbase` (\n'
        '  `__row_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,\n'
        '  `__root_row_id` BIGINT,\n'
        '  `__container_row_id` BIGINT,\n'
        '  `__json_path` VARCHAR(255),\n'
        '  `order` VARCHAR(200),\n'
        '  KEY `__root_row_id_index` (`__root_row_id`),\n'
        '  KEY `order_index` (`order`)\n'
        ')'
    ) == next(sqls, None)

    assert (
        'CREATE VIEW IF NOT EXISTS `md_Part` AS (\n'
        '  SELECT\n'
        '    JSON_EXTRACT(`md_Container`.`__json`, `md_Part_pbase`.`__json_path`) AS `__json`,\n'
        '    `md_Part_pbase`.`__row_id`,\n'
        '    `md_Part_pbase`.`__root_row_id`,\n'
        '    `md_Part_pbase`.`__container_row_id`,\n'
        '    `md_Part_pbase`.`order`\n'
        '  FROM `md_Part_pbase`\n'
        '  JOIN `md_Container` ON `md_Container`.`__row_id` = `md_Part_pbase`.`__container_row_id`\n'
        ')'
    ) == next(sqls, None)

    assert None is next(sqls, None)


def test_get_sql_for_creating_external_index_table():
    class Target(PersistentModel):
        codes: StringArrayIndex
        ids: IntegerArrayIndex

    assert [
        join_line(
            "CREATE TABLE IF NOT EXISTS `md_Target` (",
            "  `__row_id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,",
            "  `__json` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin CHECK (JSON_VALID(`__json`)),",
            "  `codes` TEXT AS (JSON_EXTRACT(`__json`, '$.codes[*]')) STORED,",
            "  `ids` TEXT AS (JSON_EXTRACT(`__json`, '$.ids[*]')) STORED,",
            "  KEY `codes_index` (`codes`),",
            "  KEY `ids_index` (`ids`)",
            ")"
        ),
        join_line(
            "CREATE TABLE IF NOT EXISTS `md_Target_codes` (",
            "  `__row_id` BIGINT,",
            "  `__root_row_id` BIGINT,",
            "  `codes` TEXT,",
            "  KEY `__row_id_index` (`__row_id`),",
            "  KEY `codes_index` (`codes`)",
            ")"
        ),
        join_line(
            "CREATE TABLE IF NOT EXISTS `md_Target_ids` (",
            "  `__row_id` BIGINT,",
            "  `__root_row_id` BIGINT,",
            "  `ids` BIGINT,",
            "  KEY `__row_id_index` (`__row_id`),",
            "  KEY `ids_index` (`ids`)",
            ")"
        )
    ] == list(get_sql_for_creating_table(Target))


@pytest.mark.parametrize('type_, expected', [
    (str, 'TEXT'),
    (StringIndex, 'VARCHAR(200)'),
    (ConStr200, 'VARCHAR(200)'),
    (constr(), 'VARCHAR(200)'),
    (ConStr10, 'VARCHAR(10)'),
    (ConDec66, 'DECIMAL(65)'),
    (condecimal(), 'DECIMAL(65)'),
    (Decimal, 'DECIMAL(65)'),
    (int, 'BIGINT'),
    (date, 'DATE'),
    (datetime, 'DATETIME(6)'),
    (bool, 'BOOL'),
])
def test_get_field_type(type_:Type, expected:str):
    assert expected == _get_field_db_type(type_)


@pytest.mark.parametrize('items, expected', [
    (
        (
            '$.items',
            False,
            {
                'title':  (('..', '$.title'), str),
                'name':  (('$.name',), str),
                'item':  (('$.des.item',), str),
                'id':  (('$.id',), str),
            },
            '_JSON_TABLE'
        ),
f"""JSON_TABLE(
  CONTAINER.`__json`,
  '$' COLUMNS (
    NESTED PATH '$.items' COLUMNS (
      `__part_order` FOR ORDINALITY,
      `name` TEXT PATH '$.name',
      `item` TEXT PATH '$.des.item',
      `id` TEXT PATH '$.id'
    )
  )
) AS _JSON_TABLE""",
    ),
    (
        (
            '$.items',
            True,
            {
                'title':  (('..', '$.title'), str),
                'name':  (('$.data', '$.name'), str),
                'item':  (('$.data', '$.des.item'), str),
                'id':  (('$.id',), str),
            },
            '_JSON_TABLE'
        ),
f"""JSON_TABLE(
  CONTAINER.`__json`,
  '$' COLUMNS (
    NESTED PATH '$.items[*]' COLUMNS (
      `__part_order` FOR ORDINALITY,
      `id` TEXT PATH '$.id',
      NESTED PATH '$.data' COLUMNS (
        `name` TEXT PATH '$.name',
        `item` TEXT PATH '$.des.item'
      )
    )
  )
) AS _JSON_TABLE"""
    ),
    (
        (
            '$.items',
            True,
            {
            },
            '_JSON_TABLE'
        ),
f"""JSON_TABLE(
  CONTAINER.`__json`,
  '$' COLUMNS (
    NESTED PATH '$.items[*]' COLUMNS (
      `__part_order` FOR ORDINALITY
    )
  )
) AS _JSON_TABLE"""
    ),
])
def test_generate_json_table(items, expected:str):
    assert expected == join_line(_generate_json_table_for_part_of(*items))


def test_get_field_type_with_exception():
    class WrongType():
        pass

    with pytest.raises(RuntimeError):
        _get_field_db_type(WrongType)


def test_field_exprs():
    assert '*' == field_exprs('*')
    assert ['*', '`f`', '`f`', 'T() as T'] == list(field_exprs(['*', 'f', '`f`', 'T() as T']))


def test_get_stored_fields():
    class MyModel(PersistentModel):
        order: StringIndex

    # Container?????? ??????????????? $.part.??? $.order??? ??????.
    assert {'order': (('$.order',), StringIndex)} == get_stored_fields(MyModel)


def test_get_stored_fields_for_mro():
    class OrderModel(PersistentModel):
        _stored_fields: StoredFieldDefinitions = {
            'order': (('$.order_name',), StringIndex)
        }

    class BaseOrderModel(PersistentModel):
        _stored_fields: StoredFieldDefinitions = {
            'name': (('$.name',), StringIndex),
            'order': (('$.order',), StringIndex)
        }

    class DerivedModel1(BaseOrderModel, OrderModel):
        _stored_fields: StoredFieldDefinitions = {
            'hello': (('$.hello',), StringIndex),
        }
        pass

    # Container?????? ??????????????? $.part.??? $.order??? ??????.
    assert {
        'hello': (('$.hello',), StringIndex),
        'order': (('$.order',), StringIndex), 
        'name': (('$.name',), StringIndex)
    } == get_stored_fields(DerivedModel1)

    class DerivedModel2(OrderModel, BaseOrderModel):
        pass

    assert {
        'order': (('$.order_name',), StringIndex), 
        'name': (('$.name',), StringIndex)
    } == get_stored_fields(DerivedModel2)


def test_get_stored_fields_of_parts():
    class Part(PersistentModel, PartOfMixin['Container']):
        order: StringIndex

    class Container(PersistentModel):
        parts: List['Part'] = Field(default=[])

    update_forward_refs(Part, locals())
    update_forward_refs(Container, locals())

    # Container?????? ??????????????? $.part.??? $.order??? ??????.
    assert {'order': (('$.order',), StringIndex)} == get_stored_fields(Part)
    assert {} == get_stored_fields(Container)


def test_get_stored_fields_of_single_part():
    class SinglePart(PersistentModel, PartOfMixin['ContainerForSingle']):
        order: StringIndex

    class ContainerForSingle(PersistentModel):
        part: SinglePart 

    update_forward_refs(SinglePart, locals())

    # Container?????? ??????????????? $.part.??? $.order??? ??????.
    assert {'order': (('$.order',), StringIndex)} == get_stored_fields(SinglePart)


def test_get_stored_fields_raise_exception():
    class PathNotStartWithDollar(PersistentModel):
        _stored_fields: StoredFieldDefinitions = {
            'order': (('order_name',), StringIndex)
        }

    with pytest.raises(RuntimeError, match='.*path must start with \\$.*'):
        get_stored_fields(PathNotStartWithDollar)


def test_get_sql_for_upserting_parts_table():
    class Part(PersistentModel, PartOfMixin['Container']):
        order: StringIndex
        codes: StringArrayIndex

    class Container(PersistentModel):
        parts: List[Part] = Field(default=[])

    update_forward_refs(Part, locals())
    sqls = get_sql_for_upserting_parts_table(Container)

    assert len(sqls[Part]) == 2
    assert join_line(
        "DELETE FROM md_Part_pbase",
        "WHERE `__root_row_id` = %(__root_row_id)s"
    ) == sqls[Part][0]

    assert join_line(
        "INSERT INTO md_Part_pbase",
        "(",
        "  `__root_row_id`,",
        "  `__container_row_id`,",
        "  `__json_path`,",
        "  `order`,",
        "  `codes`",
        ")",
        "SELECT",
        "  `__root_row_id`,",
        "  `__container_row_id`,",
        "  `__json_path`,",
        "  `order`,",
        "  JSON_ARRAYAGG(`codes`) AS `codes`",
        "FROM (",  
        "  SELECT",
        "    `__part_order`,",
        "    CONTAINER.`__row_id` as `__root_row_id`,",
        "    CONTAINER.`__row_id` as `__container_row_id`,",
        "    CONCAT('$.parts[', `__part_order` - 1, ']') as `__json_path`,",
        "    `__PART_JSON_TABLE`.`order`,",
        "    `__PART_JSON_TABLE`.`codes`",
        "  FROM",
        "    md_Container as CONTAINER,",
        "    JSON_TABLE(",
        "      CONTAINER.`__json`,",
        "      '$' COLUMNS (",
        "        NESTED PATH '$.parts[*]' COLUMNS (",
        "          `__part_order` FOR ORDINALITY,",
        "          `order` VARCHAR(200) PATH '$.order',",
        "          NESTED PATH '$.codes[*]' COLUMNS (",
        "            `codes` TEXT PATH '$'",
        "          )",
        "        )",
        "      )",    
        "    ) AS __PART_JSON_TABLE",
        "  WHERE",
        "    CONTAINER.`__row_id` = %(__root_row_id)s",
        ") AS T1",
        "GROUP BY",
        "  `__container_row_id`,",
        "  `__part_order`",
    ) == sqls[Part][1]


def test_get_sql_for_upserting_parts_table_with_container_fields():
    class Part(PersistentModel, PartOfMixin['Container']):
        _stored_fields: ClassVar[StoredFieldDefinitions]  = {
            '_container_name': (('..', '$.name'), StringIndex)
        }

    class Container(PersistentModel):
        name: StringIndex
        parts: List[Part] = Field(default=[])

    update_forward_refs(Part, locals())
    sqls = get_sql_for_upserting_parts_table(Container)

    assert len(sqls[Part]) == 2
    assert join_line(
        "DELETE FROM md_Part_pbase",
        "WHERE `__root_row_id` = %(__root_row_id)s"
    ) == sqls[Part][0]

    assert join_line(
        "INSERT INTO md_Part_pbase",
        "(",
        "  `__root_row_id`,",
        "  `__container_row_id`,",
        "  `__json_path`,",
        "  `_container_name`",
        ")",
        "SELECT",
        "  `__root_row_id`,",
        "  `__container_row_id`,",
        "  `__json_path`,",
        "  `_container_name`",
        "FROM (",  
        "  SELECT",
        "    `__part_order`,",
        "    CONTAINER.`__row_id` as `__root_row_id`,",
        "    CONTAINER.`__row_id` as `__container_row_id`,",
        "    CONCAT('$.parts[', `__part_order` - 1, ']') as `__json_path`,",
        "    JSON_VALUE(`CONTAINER`.`__json`, '$.name') as `_container_name`",
        "  FROM",
        "    md_Container as CONTAINER,",
        "    JSON_TABLE(",
        "      CONTAINER.`__json`,",
        "      '$' COLUMNS (",
        "        NESTED PATH '$.parts[*]' COLUMNS (",
        "          `__part_order` FOR ORDINALITY",
        "        )",
        "      )",    
        "    ) AS __PART_JSON_TABLE",
        "  WHERE",
        "    CONTAINER.`__row_id` = %(__root_row_id)s",
        ") AS T1",
        "GROUP BY",
        "  `__container_row_id`,",
        "  `__part_order`",
    ) == sqls[Part][1]



def test_get_sql_for_upserting_external_index_table():
    class Part(PersistentModel, PartOfMixin['Container']):
        _stored_fields: StoredFieldDefinitions = {
            '_names': (('..', '$.names', '$'), StringArrayIndex)
        }

        order: StringIndex
        codes: StringArrayIndex

    class Container(PersistentModel):
        names: List[str]
        parts: List[Part] = Field(default=[])

    update_forward_refs(Part, locals())
    sqls = list(get_sql_for_upserting_external_index_table(Part))

    assert len(sqls) == 4
    assert join_line(
        "DELETE FROM md_Part_codes",
        "WHERE `__root_row_id` = %(__root_row_id)s"
    ) == sqls[0]

    assert join_line(
        "INSERT INTO md_Part_codes",
        "(",
        "  `__root_row_id`,",
        "  `__row_id`,",
        "  `codes`",
        ")",
        "SELECT",
        "  `__ORG`.`__root_row_id`,",
        "  `__ORG`.`__row_id`,",
        "  `__EXT_JSON_TABLE`.`codes`",
        "FROM",  
        "  md_Part AS __ORG,",
        "  JSON_TABLE(",
        "    `__ORG`.`__json`,",
        "    '$' COLUMNS (",
        "      NESTED PATH '$.codes[*]' COLUMNS (",
        "        `__part_order` FOR ORDINALITY,",
        "        `codes` TEXT PATH '$'",
        "      )",    
        "    )",    
        "  ) AS __EXT_JSON_TABLE",
        "WHERE",
        "  `__ORG`.`__root_row_id` = %(__root_row_id)s",
    ) == sqls[1]

    assert join_line(
        "DELETE FROM md_Part__names",
        "WHERE `__root_row_id` = %(__root_row_id)s"
    ) == sqls[2]

    assert join_line(
        "INSERT INTO md_Part__names",
        "(",
        "  `__root_row_id`,",
        "  `__row_id`,",
        "  `_names`",
        ")",
        "SELECT",
        "  `__ORG`.`__root_row_id`,",
        "  `__ORG`.`__row_id`,",
        "  `__EXT_JSON_TABLE`.`_names`",
        "FROM",  
        "  md_Part AS __ORG,",
        "  JSON_TABLE(",
        "    `__ORG`.`_names`,",
        "    '$[*]' COLUMNS (",
        "      `_names` TEXT PATH '$'",
        "    )",    
        "  ) AS __EXT_JSON_TABLE",
        "WHERE",
        "  `__ORG`.`__root_row_id` = %(__root_row_id)s",
    ) == sqls[3]


def test_get_sql_for_upserting_parts_table_throws_if_invalid_path():
    class InvalidPath(PersistentModel, PartOfMixin['MyModel']):
        _stored_fields: ClassVar[StoredFieldDefinitions] = {
            '_invalid': (('..',), StringIndex)
        }

    class MyModel(PersistentModel):
        paths: InvalidPath

    update_forward_refs(InvalidPath, locals())

    with pytest.raises(RuntimeError, match='.*2.*items'):
        get_sql_for_upserting_parts_table(MyModel)


def test_get_query_and_args_for_reading_for_matching():
    class MyModel(PersistentModel):
        order: FullTextSearchedStr
        name: FullTextSearchedStr

    sql, args = get_query_and_args_for_reading(MyModel, ('order',), (('', 'match', '+FAST'),))

    print(sql)

    assert join_line (
        "SELECT",
        "  `_MAIN`.`order`",
        "FROM",
        "  (",
        "    SELECT",
        "      `__row_id`,",
        "      `__relevance`",
        "    FROM",    
        "    (",
        "      SELECT",
        "        `__row_id`,",
        "        `__relevance` AS `__relevance`",
        "      FROM",
        "        (",
        "          SELECT",
        "            `__ORG`.`__row_id`,",
        "            MATCH (`__ORG`.`order`,`__ORG`.`name`) AGAINST (%(ORDER_NAME)s IN BOOLEAN MODE) as `__relevance`",
        "          FROM",
        "            md_MyModel AS __ORG",
        "        )",
        "        AS __BASE",
        "    )",
        "    AS FOR_ORDERING",
        "    WHERE",
        "      `__relevance`",
        "    ORDER BY",
        "      `__relevance` DESC",
        "    LIMIT 100000000000",
        "  )",
        "  AS _BASE",
        "  JOIN md_MyModel AS _MAIN ON `_BASE`.`__row_id` = `_MAIN`.`__row_id`"
    ) == sql

    assert {
        "ORDER_NAME": "+FAST"
    } == args


def test_get_query_and_args_for_reading_for_order_by():
    class MyModel(PersistentModel):
        order: FullTextSearchedStr
        name: FullTextSearchedStr

    sql, _ = get_query_and_args_for_reading(MyModel, ('order',), tuple(), order_by=('order desc', 'name'))

    print(sql)

    assert join_line(
        "SELECT",
        "  `_BASE`.`order`",
        "FROM",
        "  (",
        "    SELECT",
        "      `__row_id`,",
        "      `order`,",
        "      `name`",
        "    FROM",
        "    (",
        "      SELECT",
        "        `__row_id`,",
        "        `order`,",
        "        `name`",
        "      FROM",
        "        (",
        "          SELECT",
        "            `__ORG`.`__row_id`,",
        "            `__ORG`.`order`,",
        "            `__ORG`.`name`",
        "          FROM",
        "            md_MyModel AS __ORG",
        "        )",
        "        AS __BASE",
        "    )",
        "    AS FOR_ORDERING",
        "    ORDER BY",
        "      `order` desc,",
        "      `name`",
        "    LIMIT 100000000000",
        "  )",
        "  AS _BASE"
    ) == sql


def test_build_query_for_core_table():
    class Model(PersistentModel):
        codes: StringArrayIndex
        name: FullTextSearchedStr
        description: FullTextSearchedStr

    query, fields = _build_query_and_fields_for_core_table('', Model, 
        ['description'], 
        (('codes', '='), ('name', '!=')),
        tuple()
    )

    assert join_line(
        'SELECT',
        '  `__ORG`.`__row_id`,',
        '  `__ORG`.`description`,',
        '  `__ORG`.`codes`,',
        '  `__ORG`.`name`',
        'FROM',
        '  md_Model AS __ORG',
        'WHERE',
        '  `__ORG`.`codes` = %(CODES)s',
        '  AND `__ORG`.`name` != %(NAME)s'
    ) == query
    assert ('__row_id', 'description', 'codes', 'name') == fields


def test_build_query_for_core_table_for_unwind():
    class Model(PersistentModel):
        codes: StringArrayIndex
        name: FullTextSearchedStr
        description: FullTextSearchedStr

    query, fields = _build_query_and_fields_for_core_table('ns', Model, 
        ['description'],
        (('codes', '='), ('name', '!=')),
        ('codes',)
    )

    assert join_line(
        'SELECT',
        '  `__ORG`.`__row_id` AS `ns.__row_id`,',
        '  `__ORG`.`description` AS `ns.description`,',
        '  `__ORG`.`name` AS `ns.name`,',
        '  `__UNWIND_CODES`.`codes` AS `ns.codes`',
        'FROM',
        '  md_Model AS __ORG',
        '  LEFT JOIN md_Model_codes AS __UNWIND_CODES ON `__ORG`.`__row_id` = `__UNWIND_CODES`.`__row_id`',
        'WHERE',
        '  `__UNWIND_CODES`.`codes` = %(NS_CODES)s',
        '  AND `__ORG`.`name` != %(NS_NAME)s'
    ) == query

    assert ('ns.__row_id', 'ns.description', 'ns.name', 'ns.codes') == fields


def test_build_query_for_core_table_for_match():
    class Model(PersistentModel):
        codes: StringArrayIndex
        name: FullTextSearchedStr
        description: FullTextSearchedStr
    
    query, fields = _build_query_and_fields_for_core_table('ns', Model, 
        [],
        (('codes', '='), ('name,description', 'match')),
        ('codes',)
    )

    assert join_line(
        'SELECT',
        '  `__ORG`.`__row_id` AS `ns.__row_id`,',
        '  `__UNWIND_CODES`.`codes` AS `ns.codes`,',
        '  MATCH (`__ORG`.`name`,`__ORG`.`description`) AGAINST (%(NAME_DESCRIPTION)s IN BOOLEAN MODE) as `ns.__relevance`',
        'FROM',
        '  md_Model AS __ORG',
        '  LEFT JOIN md_Model_codes AS __UNWIND_CODES ON `__ORG`.`__row_id` = `__UNWIND_CODES`.`__row_id`',
        'WHERE',
        '  `__UNWIND_CODES`.`codes` = %(NS_CODES)s',
    ) == query

    assert ('ns.__row_id', 'ns.' + _RELEVANCE_FIELD, 'ns.codes') == fields


def test_build_query_for_core_table_for_multiple_match():
    class Model(PersistentModel):
        codes: StringArrayIndex
        name: FullTextSearchedStr
        description: FullTextSearchedStr
 
    query, fields = _build_query_and_fields_for_core_table('', Model, 
        [],
        (('name', 'match'), ('description', 'match',)),
        tuple()
    )

    assert join_line(
        'SELECT',
        '  `__ORG`.`__row_id`,',
        '  MATCH (`__ORG`.`name`) AGAINST (%(NAME)s IN BOOLEAN MODE) + MATCH (`__ORG`.`description`) AGAINST (%(DESCRIPTION)s IN BOOLEAN MODE) as `__relevance`',
        'FROM',
        '  md_Model AS __ORG',
    ) == query

    assert ('__row_id', _RELEVANCE_FIELD) == fields


def test_extract_fields():
    fields = ('test', 'prefix.field1', 'prefix.prefix2.field', 'prefix.field2')

    assert ('test',) == _extract_fields(fields, '')
    assert ('field1', 'field2') == _extract_fields(fields, 'prefix')
    assert ('field',) == _extract_fields(fields, 'prefix.prefix2')


def test_build_join():
    class ReferencedByName(PersistentModel):
        name: StringIndex

    class NameReference(StringReference[ReferencedByName]):
        _target_field = 'name'

    class ReferencedByCode(PersistentModel):
        code: StringIndex
        name: NameReference

    class CodeReference(StringReference[ReferencedByCode]):
        _target_field = 'code'

    class ReferencedById(PersistentModel):
        id: IntIndex

    class IdReference(StringReference[ReferencedById]):
        _target_field = 'id'

    class StartModel(PersistentModel):
        code: CodeReference
        id: IdReference
        name: StringIndex

    assert [
        ('', StartModel),
        ('code', ReferencedByCode)
    ] == list(_build_namespace_types(StartModel, {}, {'code'}))

    assert [
        ('', StartModel),
        ('code', ReferencedByCode),
        ('code.name', ReferencedByName),
        ('id', ReferencedById)
    ] == list(_build_namespace_types(StartModel, {}, {'code.name', 'id'}))

    assert [
        ('', ReferencedById),
        ('start', StartModel),
        ('start.code', ReferencedByCode),
        ('start.code.name', ReferencedByName)
    ] == list(_build_namespace_types(ReferencedById, {'start': StartModel}, {'start.code.name'}))


def test_find_join_keys():
    class ReferencedByName(PersistentModel):
        name_ref: StringIndex

    class NameReference(StringReference[ReferencedByName]):
        _target_field = 'name_ref'

    class ReferencedByCode(PersistentModel):
        code: StringIndex
        name: NameReference

    class CodeReference(StringReference[ReferencedByCode]):
        _target_field = 'code'

    class ReferencedById(PersistentModel):
        id: IntIndex

    class IdReference(StringReference[ReferencedById]):
        _target_field = 'id'

    class StartModel(PersistentModel):
        code: CodeReference
        id: IdReference
        name: StringIndex

    assert {
    } == _find_join_keys((('',StartModel),))

    assert {
        (StartModel, ReferencedByCode) : ('code', 'code')
    } == _find_join_keys((('',StartModel), ('code',ReferencedByCode)))

    assert {
        (ReferencedById, StartModel) : ('id', 'id'),
        (StartModel, ReferencedByCode) : ('code', 'code'),
        (ReferencedByCode, ReferencedByName) : ('name', 'name_ref')
    } == _find_join_keys((
        ('', ReferencedById),
        ('start', StartModel), 
        ('start.code', ReferencedByCode), 
        ('start.code.name', ReferencedByName)
    ))

    with pytest.raises(RuntimeError):
        _find_join_keys((('',StartModel),('name', ReferencedByName)))

