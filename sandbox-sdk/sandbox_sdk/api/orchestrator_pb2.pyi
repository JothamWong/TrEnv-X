from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SandboxState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNSPECIFY: _ClassVar[SandboxState]
    INVALID: _ClassVar[SandboxState]
    RUNNING: _ClassVar[SandboxState]
    STOP: _ClassVar[SandboxState]
    CLEANNING: _ClassVar[SandboxState]
    SNAPSHOTTING: _ClassVar[SandboxState]
    ORPHAN: _ClassVar[SandboxState]
UNSPECIFY: SandboxState
INVALID: SandboxState
RUNNING: SandboxState
STOP: SandboxState
CLEANNING: SandboxState
SNAPSHOTTING: SandboxState
ORPHAN: SandboxState

class SandboxInfo(_message.Message):
    __slots__ = ("sandboxID", "templateID", "kernelVersion", "pid", "fcNetworkIdx", "privateIP", "startTime", "enableDiffSnapshots", "state", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    TEMPLATEID_FIELD_NUMBER: _ClassVar[int]
    KERNELVERSION_FIELD_NUMBER: _ClassVar[int]
    PID_FIELD_NUMBER: _ClassVar[int]
    FCNETWORKIDX_FIELD_NUMBER: _ClassVar[int]
    PRIVATEIP_FIELD_NUMBER: _ClassVar[int]
    STARTTIME_FIELD_NUMBER: _ClassVar[int]
    ENABLEDIFFSNAPSHOTS_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    sandboxID: str
    templateID: str
    kernelVersion: str
    pid: int
    fcNetworkIdx: int
    privateIP: str
    startTime: _timestamp_pb2.Timestamp
    enableDiffSnapshots: bool
    state: SandboxState
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, sandboxID: _Optional[str] = ..., templateID: _Optional[str] = ..., kernelVersion: _Optional[str] = ..., pid: _Optional[int] = ..., fcNetworkIdx: _Optional[int] = ..., privateIP: _Optional[str] = ..., startTime: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., enableDiffSnapshots: bool = ..., state: _Optional[_Union[SandboxState, str]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class SandboxCreateRequest(_message.Message):
    __slots__ = ("templateID", "maxInstanceLength", "sandboxID", "enableDiffSnapshots", "metadata", "hypervisorBinaryPath")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEMPLATEID_FIELD_NUMBER: _ClassVar[int]
    MAXINSTANCELENGTH_FIELD_NUMBER: _ClassVar[int]
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    ENABLEDIFFSNAPSHOTS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    HYPERVISORBINARYPATH_FIELD_NUMBER: _ClassVar[int]
    templateID: str
    maxInstanceLength: int
    sandboxID: str
    enableDiffSnapshots: bool
    metadata: _containers.ScalarMap[str, str]
    hypervisorBinaryPath: str
    def __init__(self, templateID: _Optional[str] = ..., maxInstanceLength: _Optional[int] = ..., sandboxID: _Optional[str] = ..., enableDiffSnapshots: bool = ..., metadata: _Optional[_Mapping[str, str]] = ..., hypervisorBinaryPath: _Optional[str] = ...) -> None: ...

class SandboxCreateResponse(_message.Message):
    __slots__ = ("info",)
    INFO_FIELD_NUMBER: _ClassVar[int]
    info: SandboxInfo
    def __init__(self, info: _Optional[_Union[SandboxInfo, _Mapping]] = ...) -> None: ...

class SandboxListRequest(_message.Message):
    __slots__ = ("orphan", "running")
    ORPHAN_FIELD_NUMBER: _ClassVar[int]
    RUNNING_FIELD_NUMBER: _ClassVar[int]
    orphan: bool
    running: bool
    def __init__(self, orphan: bool = ..., running: bool = ...) -> None: ...

class SandboxListResponse(_message.Message):
    __slots__ = ("sandboxes",)
    SANDBOXES_FIELD_NUMBER: _ClassVar[int]
    sandboxes: _containers.RepeatedCompositeFieldContainer[SandboxInfo]
    def __init__(self, sandboxes: _Optional[_Iterable[_Union[SandboxInfo, _Mapping]]] = ...) -> None: ...

class SandboxDeleteRequest(_message.Message):
    __slots__ = ("sandboxID",)
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    sandboxID: str
    def __init__(self, sandboxID: _Optional[str] = ...) -> None: ...

class SandboxDeactivateRequest(_message.Message):
    __slots__ = ("sandboxID",)
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    sandboxID: str
    def __init__(self, sandboxID: _Optional[str] = ...) -> None: ...

class SandboxSearchRequest(_message.Message):
    __slots__ = ("sandboxID",)
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    sandboxID: str
    def __init__(self, sandboxID: _Optional[str] = ...) -> None: ...

class SandboxSearchResponse(_message.Message):
    __slots__ = ("sandbox",)
    SANDBOX_FIELD_NUMBER: _ClassVar[int]
    sandbox: SandboxInfo
    def __init__(self, sandbox: _Optional[_Union[SandboxInfo, _Mapping]] = ...) -> None: ...

class SandboxSnapshotRequest(_message.Message):
    __slots__ = ("sandboxID", "delete")
    SANDBOXID_FIELD_NUMBER: _ClassVar[int]
    DELETE_FIELD_NUMBER: _ClassVar[int]
    sandboxID: str
    delete: bool
    def __init__(self, sandboxID: _Optional[str] = ..., delete: bool = ...) -> None: ...

class SandboxSnapshotResponse(_message.Message):
    __slots__ = ("path",)
    PATH_FIELD_NUMBER: _ClassVar[int]
    path: str
    def __init__(self, path: _Optional[str] = ...) -> None: ...

class SandboxPurgeRequest(_message.Message):
    __slots__ = ("purgeAll", "SandboxIDs")
    PURGEALL_FIELD_NUMBER: _ClassVar[int]
    SANDBOXIDS_FIELD_NUMBER: _ClassVar[int]
    purgeAll: bool
    SandboxIDs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, purgeAll: bool = ..., SandboxIDs: _Optional[_Iterable[str]] = ...) -> None: ...

class SandboxPurgeResponse(_message.Message):
    __slots__ = ("success", "msg")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    success: bool
    msg: str
    def __init__(self, success: bool = ..., msg: _Optional[str] = ...) -> None: ...
