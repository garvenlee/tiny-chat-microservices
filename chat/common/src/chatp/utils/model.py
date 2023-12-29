from os import close as osClose
from typing import Optional
from queue import Queue
from asyncio import Queue as AsyncIOQueue, BaseEventLoop, create_task


class ThreadsafeAsyncQueue:
    __slots__ = "queue", "sender_loop", "receiver_loop"

    def __init__(
        self,
        *,
        sender_loop: Optional[BaseEventLoop] = None,
        receiver_loop: Optional[BaseEventLoop] = None
    ):
        self.queue = Queue(maxsize=100)
        self.sender_loop = sender_loop
        self.receiver_loop = receiver_loop

    def bind_sender_loop(self, sender_loop: BaseEventLoop):
        self.sender_loop = sender_loop

    def bind_receiver_loop(self, receiver_loop: BaseEventLoop):
        self.receiver_loop = receiver_loop

    async def put(self, data):
        await self.sender_loop.run_in_executor(None, self.queue.put, data)

    async def get(self):
        return await self.receiver_loop.run_in_executor(None, self.queue.get)


class AsyncIOQueueWriterWrapper:
    __slots__ = "write"

    def __init__(self, queue: AsyncIOQueue):
        self.write = queue.put_nowait


class ThreadsafeQueueWriterWrapper:
    __slots__ = "dest_queue", "transfer_queue", "write", "task"

    def __init__(self, queue: ThreadsafeAsyncQueue):
        self.dest_queue = queue
        self.transfer_queue = AsyncIOQueue()
        self.write = self.transfer_queue.put_nowait

        self.task = create_task(self.transfer())

    async def transfer(self):
        transfer_queue_get = self.transfer_queue.get
        dest_queue_put = self.dest_queue.put
        while True:
            data = await transfer_queue_get()
            await dest_queue_put(data)

    # TODO
    def close(self):
        pass


class FdWrapper:
    __slot__ = "fd"

    def __init__(self, fd: int):
        self.fd = fd

    def fileno(self):
        return self.fd

    def close(self):
        osClose(self.fd)
