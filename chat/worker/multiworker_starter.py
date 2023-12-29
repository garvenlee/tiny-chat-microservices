from asyncio import Future, run
from chatp.starter import create_starter, move_on_starter
from chatp.entrypoint import AsyncMultiProcessManager


async def main(starter: AsyncMultiProcessManager):
    def handle_exit(*args, **kwargs) -> None:
        nonlocal waiter
        if not waiter.done():
            waiter.set_result(None)

    starter.handle_exit = handle_exit  # multiworker
    # starter.main_executor_complete_cb = handle_exit  # single worker
    async with move_on_starter(starter):
        waiter = Future()
        await waiter


if __name__ == "__main__":
    from sys import argv as sys_argv

    assert len(sys_argv) == 3, "Only support one argname: --worker-type[-W]"
    assert sys_argv[1] in (
        "--worker-type",
        "-W",
    ), "The only argname must be one of [--worker-type, -W]"
    worker_type = sys_argv[2]
    match worker_type:
        case "FriendToPsql":
            conf_path = "./confs/friend_to_psql.yaml"
            from impl.friend_to_psql_worker import serve
        case "FriendToPush":
            conf_path = "./confs/friend_to_push.yaml"
            from impl.friend_to_push_worker import serve
        case "MessageConsumer":
            conf_path = "./confs/message_consumer.yaml"
            from impl.msg_consumer_worker import serve
        case "MessageDLQ":
            conf_path = "./confs/message_dlq.yaml"
            from impl.dlq_worker import serve
        case _:
            raise NotImplementedError(f"Unsupported worker-type: {worker_type}")

    import uvloop

    uvloop.install()

    with create_starter(
        conf_path,
        worker_factory=serve,
        handle_exit=None,
    ) as starter:
        run(main(starter))
