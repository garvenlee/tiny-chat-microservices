# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from . import redis_cache_pb2 as redis__cache__pb2


class RedisCacheStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.RedisGet = channel.unary_unary(
            "/RedisCache/RedisGet",
            request_serializer=redis__cache__pb2.UnaryGetCommonRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.UnaryGetCommonResp.FromString,
        )
        self.RedisSet = channel.unary_unary(
            "/RedisCache/RedisSet",
            request_serializer=redis__cache__pb2.UnarySetCommonRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.UnarySetCommonResp.FromString,
        )
        self.RedisMGet = channel.unary_unary(
            "/RedisCache/RedisMGet",
            request_serializer=redis__cache__pb2.MultiGetCommonRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.MultiGetCommonResp.FromString,
        )
        self.RedisMSet = channel.unary_unary(
            "/RedisCache/RedisMSet",
            request_serializer=redis__cache__pb2.MultiSetCommonRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.MultiSetCommonResp.FromString,
        )
        self.RedisLPush = channel.unary_unary(
            "/RedisCache/RedisLPush",
            request_serializer=redis__cache__pb2.RedisListPushRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisListPushResp.FromString,
        )
        self.RedisRPush = channel.unary_unary(
            "/RedisCache/RedisRPush",
            request_serializer=redis__cache__pb2.RedisListPushRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisListPushResp.FromString,
        )
        self.RedisHLen = channel.unary_unary(
            "/RedisCache/RedisHLen",
            request_serializer=redis__cache__pb2.UnaryGetCommonResp.SerializeToString,
            response_deserializer=redis__cache__pb2.UnaryGetCommonResp.FromString,
        )
        self.RedisHGet = channel.unary_unary(
            "/RedisCache/RedisHGet",
            request_serializer=redis__cache__pb2.RedisHGetRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisHGetResp.FromString,
        )
        self.RedisHSet = channel.unary_unary(
            "/RedisCache/RedisHSet",
            request_serializer=redis__cache__pb2.RedisHSetRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisHSetResp.FromString,
        )
        self.RedisHDel = channel.unary_unary(
            "/RedisCache/RedisHDel",
            request_serializer=redis__cache__pb2.RedisHDelRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisHDelResp.FromString,
        )
        self.RedisHGetAll = channel.unary_unary(
            "/RedisCache/RedisHGetAll",
            request_serializer=redis__cache__pb2.RedisHGetRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisHGetAllResp.FromString,
        )
        self.RedisDelete = channel.unary_unary(
            "/RedisCache/RedisDelete",
            request_serializer=redis__cache__pb2.RedisDeleteRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisDeleteResp.FromString,
        )
        self.RedisRateLimiter = channel.unary_unary(
            "/RedisCache/RedisRateLimiter",
            request_serializer=redis__cache__pb2.RedisRateLimiterRequest.SerializeToString,
            response_deserializer=redis__cache__pb2.RedisRateLimiterResp.FromString,
        )


class RedisCacheServicer(object):
    """Missing associated documentation comment in .proto file."""

    def RedisGet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisSet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisMGet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisMSet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisLPush(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisRPush(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisHLen(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisHGet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisHSet(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisHDel(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisHGetAll(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisDelete(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def RedisRateLimiter(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_RedisCacheServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "RedisGet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisGet,
            request_deserializer=redis__cache__pb2.UnaryGetCommonRequest.FromString,
            response_serializer=redis__cache__pb2.UnaryGetCommonResp.SerializeToString,
        ),
        "RedisSet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisSet,
            request_deserializer=redis__cache__pb2.UnarySetCommonRequest.FromString,
            response_serializer=redis__cache__pb2.UnarySetCommonResp.SerializeToString,
        ),
        "RedisMGet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisMGet,
            request_deserializer=redis__cache__pb2.MultiGetCommonRequest.FromString,
            response_serializer=redis__cache__pb2.MultiGetCommonResp.SerializeToString,
        ),
        "RedisMSet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisMSet,
            request_deserializer=redis__cache__pb2.MultiSetCommonRequest.FromString,
            response_serializer=redis__cache__pb2.MultiSetCommonResp.SerializeToString,
        ),
        "RedisLPush": grpc.unary_unary_rpc_method_handler(
            servicer.RedisLPush,
            request_deserializer=redis__cache__pb2.RedisListPushRequest.FromString,
            response_serializer=redis__cache__pb2.RedisListPushResp.SerializeToString,
        ),
        "RedisRPush": grpc.unary_unary_rpc_method_handler(
            servicer.RedisRPush,
            request_deserializer=redis__cache__pb2.RedisListPushRequest.FromString,
            response_serializer=redis__cache__pb2.RedisListPushResp.SerializeToString,
        ),
        "RedisHLen": grpc.unary_unary_rpc_method_handler(
            servicer.RedisHLen,
            request_deserializer=redis__cache__pb2.UnaryGetCommonResp.FromString,
            response_serializer=redis__cache__pb2.UnaryGetCommonResp.SerializeToString,
        ),
        "RedisHGet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisHGet,
            request_deserializer=redis__cache__pb2.RedisHGetRequest.FromString,
            response_serializer=redis__cache__pb2.RedisHGetResp.SerializeToString,
        ),
        "RedisHSet": grpc.unary_unary_rpc_method_handler(
            servicer.RedisHSet,
            request_deserializer=redis__cache__pb2.RedisHSetRequest.FromString,
            response_serializer=redis__cache__pb2.RedisHSetResp.SerializeToString,
        ),
        "RedisHDel": grpc.unary_unary_rpc_method_handler(
            servicer.RedisHDel,
            request_deserializer=redis__cache__pb2.RedisHDelRequest.FromString,
            response_serializer=redis__cache__pb2.RedisHDelResp.SerializeToString,
        ),
        "RedisHGetAll": grpc.unary_unary_rpc_method_handler(
            servicer.RedisHGetAll,
            request_deserializer=redis__cache__pb2.RedisHGetRequest.FromString,
            response_serializer=redis__cache__pb2.RedisHGetAllResp.SerializeToString,
        ),
        "RedisDelete": grpc.unary_unary_rpc_method_handler(
            servicer.RedisDelete,
            request_deserializer=redis__cache__pb2.RedisDeleteRequest.FromString,
            response_serializer=redis__cache__pb2.RedisDeleteResp.SerializeToString,
        ),
        "RedisRateLimiter": grpc.unary_unary_rpc_method_handler(
            servicer.RedisRateLimiter,
            request_deserializer=redis__cache__pb2.RedisRateLimiterRequest.FromString,
            response_serializer=redis__cache__pb2.RedisRateLimiterResp.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "RedisCache", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


# This class is part of an EXPERIMENTAL API.
class RedisCache(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def RedisGet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisGet",
            redis__cache__pb2.UnaryGetCommonRequest.SerializeToString,
            redis__cache__pb2.UnaryGetCommonResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisSet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisSet",
            redis__cache__pb2.UnarySetCommonRequest.SerializeToString,
            redis__cache__pb2.UnarySetCommonResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisMGet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisMGet",
            redis__cache__pb2.MultiGetCommonRequest.SerializeToString,
            redis__cache__pb2.MultiGetCommonResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisMSet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisMSet",
            redis__cache__pb2.MultiSetCommonRequest.SerializeToString,
            redis__cache__pb2.MultiSetCommonResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisLPush(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisLPush",
            redis__cache__pb2.RedisListPushRequest.SerializeToString,
            redis__cache__pb2.RedisListPushResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisRPush(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisRPush",
            redis__cache__pb2.RedisListPushRequest.SerializeToString,
            redis__cache__pb2.RedisListPushResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisHLen(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisHLen",
            redis__cache__pb2.UnaryGetCommonResp.SerializeToString,
            redis__cache__pb2.UnaryGetCommonResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisHGet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisHGet",
            redis__cache__pb2.RedisHGetRequest.SerializeToString,
            redis__cache__pb2.RedisHGetResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisHSet(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisHSet",
            redis__cache__pb2.RedisHSetRequest.SerializeToString,
            redis__cache__pb2.RedisHSetResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisHDel(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisHDel",
            redis__cache__pb2.RedisHDelRequest.SerializeToString,
            redis__cache__pb2.RedisHDelResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisHGetAll(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisHGetAll",
            redis__cache__pb2.RedisHGetRequest.SerializeToString,
            redis__cache__pb2.RedisHGetAllResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisDelete(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisDelete",
            redis__cache__pb2.RedisDeleteRequest.SerializeToString,
            redis__cache__pb2.RedisDeleteResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def RedisRateLimiter(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        insecure=False,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/RedisCache/RedisRateLimiter",
            redis__cache__pb2.RedisRateLimiterRequest.SerializeToString,
            redis__cache__pb2.RedisRateLimiterResp.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )
