# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: snowflake.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x0fsnowflake.proto\x12\x12services.snowflake"B\n\x10SnowflakeRequest\x12.\n\x04kind\x18\x01 \x01(\x0e\x32 .services.snowflake.BusinessKind"&\n\x0eSnowflakeReply\x12\x14\n\x0csnowflake_id\x18\x01 \x01(\x03*X\n\x0c\x42usinessKind\x12\x15\n\x11SNOWFLAKE_SESSION\x10\x00\x12\x15\n\x11SNOWFLAKE_MESSAGE\x10\x01\x12\x1a\n\x16SNOWFLAKE_USER_DEFINED\x10\x02\x32\x65\n\tSnowflake\x12X\n\nflickClock\x12$.services.snowflake.SnowflakeRequest\x1a".services.snowflake.SnowflakeReply"\x00\x62\x06proto3'
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "snowflake_pb2", _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals["_BUSINESSKIND"]._serialized_start = 147
    _globals["_BUSINESSKIND"]._serialized_end = 235
    _globals["_SNOWFLAKEREQUEST"]._serialized_start = 39
    _globals["_SNOWFLAKEREQUEST"]._serialized_end = 105
    _globals["_SNOWFLAKEREPLY"]._serialized_start = 107
    _globals["_SNOWFLAKEREPLY"]._serialized_end = 145
    _globals["_SNOWFLAKE"]._serialized_start = 237
    _globals["_SNOWFLAKE"]._serialized_end = 338
# @@protoc_insertion_point(module_scope)