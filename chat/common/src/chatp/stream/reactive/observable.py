# from reactivex.observable import Observable
# from reactivex.observer import Observer
# from faust import streams


class Observable:
    def __init__(self, subscribe):
        self._subscribe = subscribe

    def feed_data(self):
        pass

    # data source -> operations -> observer
    def subscribe(self):
        pass

    def pipe(self, *operations):
        pass
