class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        return cls._instances.setdefault(
            cls, super(SingletonMeta, cls).__call__(*args, **kwargs)
        )


if __name__ == "__main__":

    class A(metaclass=SingletonMeta):
        pass

    print(A() is A())
