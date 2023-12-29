from logging import getLogger
from types import FunctionType
from typing import Callable
from functools import wraps

from grpc import StatusCode
from grpc.aio._call import AioRpcError
from grpc.aio._base_server import ServicerContext as AioServicerContext
from google.protobuf.message import Message as ProtobufMessage
from aiomisc.circuit_breaker import CircuitBreaker, CircuitBroken

# from grpc_status import rpc_status

from .model import *


ABORTED = StatusCode.ABORTED
CANCELLED = StatusCode.CANCELLED
UNAVAILABLE = StatusCode.UNAVAILABLE
DEADLINE_EXCEEDED = StatusCode.DEADLINE_EXCEEDED
RESOURCE_EXHAUSTED = StatusCode.RESOURCE_EXHAUSTED


def exception_inspector(exc: AioRpcError):
    return exc.code() in (UNAVAILABLE, RESOURCE_EXHAUSTED, DEADLINE_EXCEEDED)


def depend(stub_cls):
    def wrapper(wrapped: FunctionType):
        wrapped.__annotations__["depend_stub"] = stub_cls
        return wrapped

    return wrapper


# wrapped is grpc `callable`: [request, context=None] -> response
def grpc_wrapper_with_kwargs(
    wrapped: Callable[[ProtobufMessage, AioServicerContext], ProtobufMessage],
    func_defination: FunctionType,
    service_name: str,
    circuit_breaker: CircuitBreaker,
):
    anno = func_defination.__annotations__
    request_cls = anno["request"]
    # response_cls = anno["return"]

    request_desc = request_cls.DESCRIPTOR
    # response_desc = response_cls.DESCRIPTOR

    request_slots = tuple(request_desc.fields_by_name.keys())
    # response_slots = tuple(response_desc.fields_by_name.keys())

    num_request_slots = len(request_slots)
    func_name = func_defination.__name__
    logger = getLogger(service_name)
    logger.setLevel(10)

    @wraps(wrapped)
    async def inner_func(*args, timeout=5, **kwargs) -> CallResult:
        # args have the only one val, that is self
        if len(args) > 2:
            info = f"{func_name}: wrapped args must be keyword args."
            logger.warning(info)
            return CallResult(status=GRPC_INTERFACE_ERROR, info=info)
            # self = args[0]  # Service class's instance

        # firstly, construct request obj with args validation
        if len(kwargs) == num_request_slots:
            fields = tuple(filter(lambda field: field not in kwargs, request_slots))
            if not fields:
                try:
                    request = request_cls(**kwargs)
                except TypeError as e:  # set the wrong type
                    logger.warning(f"{func_name}: {e.args[0]}")
                    return CallResult(GRPC_ARGS_TYPE_ERROR, info=info)
                else:
                    try:
                        with circuit_breaker.context():
                            response = await wrapped(request, timeout=timeout)
                    except AioRpcError as rpc_error:
                        rpc_code = rpc_error.code()
                        logger.exception(
                            f"<{func_name}> Call failed with code: %s",
                            rpc_code,
                            exc_info=rpc_error,
                        )
                        return CallResult(
                            GRPC_TIMEOUT
                            if rpc_code is DEADLINE_EXCEEDED  # timeout
                            else GRPC_FAILED,
                            info=rpc_code,
                        )
                    except CircuitBroken as exc:
                        logger.exception(
                            f"<{func_name}> Call failed with: %s", exc, exc_info=exc
                        )
                        return CallResult(GRPC_FAILED, info="CircuitBreaker Broken")
                    except BaseException as exc:  # unknown exc
                        logger.exception(
                            f"<{func_name}> Call failed with: %s", exc, exc_info=exc
                        )
                        return CallResult(GRPC_FAILED, info=exc)
                    else:
                        logger.info(f"{func_name}: grpc called successfully")
                        return CallResult(GRPC_SUCCESS, data=response)
            else:
                info = ", ".join(fields)
                info = f"missing fields: {info}"
                logger.warning(f"{func_name}: {info}.")
                return CallResult(GRPC_ARGS_MISMATCH, info=info)
        else:
            info = f"{func_name}: wrapped args mismatched."
            logger.warning(info)
            return CallResult(
                GRPC_ARGS_MISMATCH,
                info=info,
            )

    return inner_func


# wrapped is grpc `callable`: [request, context=None] -> response
def grpc_wrapper_with_request(
    wrapped: Callable[[ProtobufMessage, AioServicerContext], ProtobufMessage],
    func_name: str,
    service_name: str,
    circuit_breaker: CircuitBreaker,
):
    logger = getLogger(service_name)

    @wraps(wrapped)
    async def inner_func(request: Message, *, timeout=5) -> CallResult:
        try:
            with circuit_breaker.context():
                response = await wrapped(request, timeout=timeout)
        except AioRpcError as rpc_error:
            rpc_code = rpc_error.code()
            logger.exception(
                f"<{func_name}> Call failed with: %s",
                rpc_code,
                exc_info=rpc_error,
            )
            return CallResult(
                GRPC_TIMEOUT if rpc_code is DEADLINE_EXCEEDED else GRPC_FAILED,
                info=rpc_code,
            )
        except CircuitBroken as exc:
            logger.exception(f"<{func_name}> Call failed with: %s", exc, exc_info=exc)
            return CallResult(GRPC_FAILED, info="CircuitBreaker Broken")
        except BaseException as exc:  # unknown exc
            logger.exception(f"<{func_name}> Call failed with: %s", exc, exc_info=exc)
            return CallResult(GRPC_FAILED, info=exc)
        else:
            logger.info(f"{func_name}: grpc called successfully.")
            return CallResult(GRPC_SUCCESS, data=response)

    return inner_func
