# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: event.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x0b\x65vent.proto\x12\x05\x63hatp"p\n\x0cServiceEvent\x12\'\n\x06srv_tp\x18\x01 \x01(\x0e\x32\x17.chatp.ServiceEventType\x12\x10\n\x08srv_name\x18\x02 \x01(\t\x12\x10\n\x08srv_addr\x18\x03 \x01(\t\x12\x13\n\x0bplatform_id\x18\x04 \x01(\t"C\n\rLoadHintEvent\x12\x10\n\x08srv_name\x18\x01 \x01(\t\x12\x10\n\x08srv_addr\x18\x02 \x01(\t\x12\x0e\n\x06weight\x18\x03 \x01(\x0c"\x9d\x01\n\x05\x45vent\x12 \n\x06\x65vt_tp\x18\x01 \x01(\x0e\x32\x10.chatp.EventType\x12&\n\x07srv_evt\x18\x02 \x01(\x0b\x32\x13.chatp.ServiceEventH\x00\x12(\n\x08load_evt\x18\x03 \x01(\x0b\x32\x14.chatp.LoadHintEventH\x00\x12\x12\n\x08user_evt\x18\x04 \x01(\x0cH\x00\x42\x0c\n\nevt_entity*>\n\tEventType\x12\x12\n\x0eSERVICE_CHANGE\x10\x00\x12\r\n\tLOAD_HINT\x10\x01\x12\x0e\n\nUSER_EVENT\x10\x02*;\n\x10ServiceEventType\x12\x12\n\x0eSERVICE_ONLINE\x10\x00\x12\x13\n\x0fSERVICE_OFFLINE\x10\x01\x62\x06proto3'
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "event_pb2", _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals["_EVENTTYPE"]._serialized_start = 365
    _globals["_EVENTTYPE"]._serialized_end = 427
    _globals["_SERVICEEVENTTYPE"]._serialized_start = 429
    _globals["_SERVICEEVENTTYPE"]._serialized_end = 488
    _globals["_SERVICEEVENT"]._serialized_start = 22
    _globals["_SERVICEEVENT"]._serialized_end = 134
    _globals["_LOADHINTEVENT"]._serialized_start = 136
    _globals["_LOADHINTEVENT"]._serialized_end = 203
    _globals["_EVENT"]._serialized_start = 206
    _globals["_EVENT"]._serialized_end = 363
# @@protoc_insertion_point(module_scope)
