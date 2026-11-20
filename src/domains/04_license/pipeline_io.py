"""Batch IO and immutable artifact publication for Domain 04."""

import csv
import hashlib
import os
import shutil
import sys
from contextlib import contextmanager
from uuid import uuid4

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from config import load_config


ROW = "source_row_num"
BATCH_SIZE = 65_536


def header_selection(header, source):
    if any(not isinstance(name, str) or not name.strip() for name in header):
        raise ValueError(f"{source.path.name}: blank or non-text column header.")
    if len(set(header)) != len(header) or ROW in header:
        raise ValueError(f"{source.path.name}: duplicate or reserved column header.")
    columns = list(source.columns) if source.columns else list(header)
    if not set(columns) <= set(header):
        raise ValueError(f"{source.path.name}: columns missing: {sorted(set(columns) - set(header))}.")
    return columns


def source_batches(source):
    if source.format == "xlsx":
        yield from excel_batches(source)
        return

    with source.path.open(encoding=source.encoding, newline="") as stream:
        header = next(csv.reader(stream), [])
        if header:
            header[0] = header[0].removeprefix("\ufeff")
        columns = header_selection(header, source)
    if not columns:
        raise ValueError(f"{source.path.name}: CSV header not found.")
    options = pacsv.ConvertOptions(
        include_columns=columns,
        column_types={column: pa.string() for column in columns},
        strings_can_be_null=False,
    )
    with pacsv.open_csv(
        source.path,
        read_options=pacsv.ReadOptions(encoding=source.encoding, block_size=8 * 1024 * 1024),
        parse_options=pacsv.ParseOptions(newlines_in_values=True, ignore_empty_lines=False),
        convert_options=options,
    ) as reader:
        yield reader.schema
        yield from reader


def excel_batches(source):
    from openpyxl import load_workbook

    book = load_workbook(source.path, read_only=True, data_only=True)
    try:
        sheet = book[source.sheet] if source.sheet else book.active
        rows = sheet.iter_rows(values_only=True)
        header = list(next(rows, ()))
        while header and header[-1] is None:
            header.pop()
        columns = header_selection(header, source)
        if not columns:
            raise ValueError(f"{source.path.name}: worksheet header not found.")
        indices = [header.index(column) for column in columns]
        schema = pa.schema([(column, pa.string()) for column in columns])
        yield schema
        batch = [[] for _ in columns]
        for row in rows:
            for values, idx in zip(batch, indices):
                value = row[idx] if idx < len(row) else None
                values.append("" if value is None else str(value))
            if len(batch[0]) == BATCH_SIZE:
                yield pa.record_batch(batch, schema=schema)
                batch = [[] for _ in columns]
        if batch[0]:
            yield pa.record_batch(batch, schema=schema)
    finally:
        book.close()


def bronze_batches(source):
    batches = iter(source_batches(source))
    schema = next(batches).append(pa.field(ROW, pa.int64()))
    yield schema
    number = 1
    for batch in batches:
        rows = pa.array(range(number, number + batch.num_rows), type=pa.int64())
        yield pa.record_batch([*batch.columns, rows], schema=schema)
        number += batch.num_rows


def parquet_batches(path, columns=None):
    with pq.ParquetFile(path) as file:
        yield from file.iter_batches(batch_size=BATCH_SIZE, columns=columns)


def write_parquet(path, schema, batches):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pq.ParquetWriter(path, schema, compression="zstd", version="2.6") as writer:
        for batch in batches:
            writer.write_batch(batch, row_group_size=BATCH_SIZE)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def staging(root, replace=False):
    if root.resolve() != root:
        raise ValueError(f"Output directory resolves outside its configured location: {root}")
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f".04-license-{uuid4().hex}"
    # On Windows a 0o700 directory has a private ACL that hard-linked outputs retain.
    tmp.mkdir(mode=0o777 if os.name == "nt" else 0o700)
    try:
        yield tmp
        files = []
        for path in sorted(tmp.rglob("*")):
            if path.is_file():
                final = root / path.relative_to(tmp)
                if final.resolve() != final:
                    raise ValueError(f"Refusing to publish through an output link: {final}")
                if not replace and final.exists() and sha256(final) != sha256(path):
                    raise ValueError(f"Output already exists with different content: {final}. Use a new output directory.")
                files.append((path, final))
        for source, final in files:
            final.parent.mkdir(parents=True, exist_ok=True)
            if replace:
                os.replace(source, final)
                continue
            try:
                os.link(source, final)
            except FileExistsError:
                if sha256(final) != sha256(source):
                    raise ValueError(f"Concurrent output differs: {final}")
    finally:
        if tmp.resolve() != tmp:
            raise ValueError(f"Refusing to remove a staging directory outside its configured location: {tmp}")
        shutil.rmtree(tmp)


def cli(action, description):
    try:
        conf = load_config(description)
        return action(conf) or 0
    except (ValueError, KeyError, OSError, pa.ArrowException) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
