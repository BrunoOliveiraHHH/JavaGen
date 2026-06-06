"""Mapeia tipos SQL (multi-dialeto) para tipos Java, extraindo length/precision/scale.

Sempre retorna um resultado válido: tipo desconhecido degrada para String + unknown=True.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class JavaType:
    java_type: str
    java_import: Optional[str]
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    unknown: bool = False


# base SQL (sem parâmetros, UPPER) -> (java_type, import)
_TYPE_MAP: dict[str, tuple[str, Optional[str]]] = {
    # Texto
    "VARCHAR": ("String", None),
    "VARCHAR2": ("String", None),
    "CHARACTER VARYING": ("String", None),
    "NVARCHAR": ("String", None),
    "CHAR": ("String", None),
    "CHARACTER": ("String", None),
    "NCHAR": ("String", None),
    "BPCHAR": ("String", None),
    "TEXT": ("String", None),
    "NTEXT": ("String", None),
    "CLOB": ("String", None),
    "CITEXT": ("String", None),
    "LONGTEXT": ("String", None),
    "MEDIUMTEXT": ("String", None),
    "TINYTEXT": ("String", None),
    # Numérico exato
    "NUMERIC": ("BigDecimal", "java.math.BigDecimal"),
    "DECIMAL": ("BigDecimal", "java.math.BigDecimal"),
    "NUMBER": ("BigDecimal", "java.math.BigDecimal"),
    "MONEY": ("BigDecimal", "java.math.BigDecimal"),
    # Inteiro 64
    "BIGINT": ("Long", None),
    "INT8": ("Long", None),
    "BIGSERIAL": ("Long", None),
    "SERIAL8": ("Long", None),
    # Inteiro 32
    "INTEGER": ("Integer", None),
    "INT": ("Integer", None),
    "INT4": ("Integer", None),
    "MEDIUMINT": ("Integer", None),
    "SERIAL": ("Integer", None),
    "SERIAL4": ("Integer", None),
    # Inteiro 16 / 8
    "SMALLINT": ("Short", None),
    "INT2": ("Short", None),
    "SMALLSERIAL": ("Short", None),
    "TINYINT": ("Short", None),
    # Ponto flutuante
    "REAL": ("Double", None),
    "FLOAT4": ("Double", None),
    "FLOAT": ("Double", None),
    "FLOAT8": ("Double", None),
    "DOUBLE": ("Double", None),
    "DOUBLE PRECISION": ("Double", None),
    "BINARY_DOUBLE": ("Double", None),
    # Boolean
    "BOOLEAN": ("Boolean", None),
    "BOOL": ("Boolean", None),
    "BIT": ("Boolean", None),
    # Data/hora
    "DATE": ("LocalDate", "java.time.LocalDate"),
    "TIME": ("LocalTime", "java.time.LocalTime"),
    "TIMETZ": ("OffsetTime", "java.time.OffsetTime"),
    "DATETIME": ("LocalDateTime", "java.time.LocalDateTime"),
    "DATETIME2": ("LocalDateTime", "java.time.LocalDateTime"),
    "SMALLDATETIME": ("LocalDateTime", "java.time.LocalDateTime"),
    "TIMESTAMP": ("LocalDateTime", "java.time.LocalDateTime"),
    "TIMESTAMPTZ": ("OffsetDateTime", "java.time.OffsetDateTime"),
    "TIMESTAMP WITH TIME ZONE": ("OffsetDateTime", "java.time.OffsetDateTime"),
    "TIMESTAMP WITHOUT TIME ZONE": ("LocalDateTime", "java.time.LocalDateTime"),
    "INTERVAL": ("Duration", "java.time.Duration"),
    # UUID
    "UUID": ("UUID", "java.util.UUID"),
    "UNIQUEIDENTIFIER": ("UUID", "java.util.UUID"),
    # Binário
    "BYTEA": ("byte[]", None),
    "BLOB": ("byte[]", None),
    "VARBINARY": ("byte[]", None),
    "BINARY": ("byte[]", None),
    "IMAGE": ("byte[]", None),
    # JSON / outros -> String
    "JSON": ("String", None),
    "JSONB": ("String", None),
    "XML": ("String", None),
    "INET": ("String", None),
    "CIDR": ("String", None),
    "MACADDR": ("String", None),
}

_UNKNOWN = "String"


def _normalize(raw: str) -> str:
    """'VARCHAR(255)' -> 'VARCHAR' ; remove [] de array."""
    base = raw.split("(")[0].strip()
    base = base.replace("[]", "").strip()
    return re.sub(r"\s+", " ", base).upper()


def _params(raw: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Extrai (length, precision, scale)."""
    m = re.search(r"\(([^)]*)\)", raw)
    if not m:
        return None, None, None
    nums = [int(x.strip()) for x in m.group(1).split(",") if x.strip().lstrip("-").isdigit()]
    base = _normalize(raw)
    if base in ("NUMERIC", "DECIMAL", "NUMBER", "MONEY"):
        precision = nums[0] if len(nums) >= 1 else None
        scale = nums[1] if len(nums) >= 2 else None
        return None, precision, scale
    length = nums[0] if nums else None
    return length, None, None


def map_type(raw_sql_type: str, dialect: str = "postgres") -> JavaType:
    raw_sql_type = (raw_sql_type or "").strip()
    base = _normalize(raw_sql_type)
    is_array = raw_sql_type.endswith("[]")

    mapped = _TYPE_MAP.get(base)
    unknown = mapped is None
    if unknown:
        java_type, imp = _UNKNOWN, None
    else:
        java_type, imp = mapped

    length, precision, scale = _params(raw_sql_type)

    if is_array:
        java_type = f"List<{java_type}>"
        imp = "java.util.List"

    return JavaType(
        java_type=java_type,
        java_import=imp,
        length=length,
        precision=precision,
        scale=scale,
        unknown=unknown,
    )
